from __future__ import annotations

import difflib
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_NOISY_GLOBS = (
    "libraries/**",
    "versions/**",
    "backups/**",
    "world/region/**",
    "world/DIM*/**",
    "world/entities/**",
    "world/poi/**",
    ".git/**",
    "cache/**",
    "crash-reports/old/**",
)
DEFAULT_BINARY_EXTENSIONS = {
    ".7z",
    ".class",
    ".dat",
    ".db",
    ".dll",
    ".dylib",
    ".exe",
    ".gz",
    ".jar",
    ".mca",
    ".ogg",
    ".pack",
    ".png",
    ".sqlite",
    ".so",
    ".wav",
    ".zip",
}
VERSION_SUFFIX_RE = re.compile(r"[-_+](?:mc)?\d[\w.+-]*$")


def configured_minecraft_root() -> Path:
    raw_root = os.getenv("MINECRAFT_SERVER_DIR", "").strip()
    if not raw_root:
        raise RuntimeError("MINECRAFT_SERVER_DIR is not set.")

    root = Path(raw_root).expanduser()
    if not root.is_absolute():
        root = root.resolve()
    else:
        root = root.resolve()

    if not root.exists():
        raise RuntimeError(f"Minecraft server root does not exist: {root}")
    if not root.is_dir():
        raise RuntimeError(f"MINECRAFT_SERVER_DIR is not a directory: {root}")
    return root


def _utc_timestamp(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def _normalize_relative_path(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return str(path)
    text = relative.as_posix()
    return text or "."


def _glob_matches(relative_path: str, pattern: str) -> bool:
    posix_path = PurePosixPath(relative_path)
    variants = [pattern]
    if pattern.endswith("/**"):
        variants.append(pattern[:-3])
    return any(posix_path.match(candidate) for candidate in variants)


def _looks_binary(path: Path) -> bool:
    if path.suffix.lower() in DEFAULT_BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return False
    return b"\x00" in chunk


def _read_text_file(path: Path, *, max_bytes: int) -> list[str]:
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"{path.name} is too large to compare safely ({size} bytes).")
    if _looks_binary(path):
        raise ValueError(f"{path.name} appears to be a binary file.")
    return path.read_text(encoding="utf-8").splitlines()


@dataclass
class MinecraftDiagnostics:
    root: Path
    rg_timeout_seconds: float = 20.0
    max_text_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        self.root = self.root.expanduser().resolve()

    @classmethod
    def from_env(cls) -> "MinecraftDiagnostics":
        return cls(
            root=configured_minecraft_root(),
            rg_timeout_seconds=max(1.0, float(os.getenv("MINECRAFT_MCP_RG_TIMEOUT", "20"))),
            max_text_bytes=max(4096, int(os.getenv("MINECRAFT_MCP_MAX_TEXT_BYTES", "1000000"))),
        )

    def resolve_path(self, requested_path: str, *, must_exist: bool = True) -> Path:
        normalized = (requested_path or ".").strip() or "."
        if normalized in {".", "/"}:
            candidate = self.root
        else:
            raw_path = Path(normalized).expanduser()
            candidate = raw_path if raw_path.is_absolute() else self.root / raw_path

        if must_exist:
            if not candidate.exists():
                raise FileNotFoundError(f"Path does not exist inside the server root: {normalized}")
            resolved = candidate.resolve()
            self._ensure_inside_root(resolved)
            return resolved

        parent = candidate.parent if candidate.name else candidate
        if not parent.exists():
            resolved_parent = parent.resolve()
            self._ensure_inside_root(resolved_parent)
            return candidate

        resolved_parent = parent.resolve()
        self._ensure_inside_root(resolved_parent)
        return candidate

    def _ensure_inside_root(self, path: Path) -> None:
        if path != self.root and self.root not in path.parents:
            raise ValueError(
                f"Refusing to access '{path}' because it resolves outside the configured "
                f"Minecraft server root '{self.root}'."
            )

    def _exclude_globs(self, extra_excludes: list[str] | None = None) -> list[str]:
        globs = list(DEFAULT_NOISY_GLOBS)
        for pattern in extra_excludes or []:
            cleaned = str(pattern or "").strip()
            if cleaned:
                globs.append(cleaned)
        return globs

    def _is_excluded(
        self,
        path: Path,
        *,
        include_hidden: bool,
        extra_excludes: list[str] | None = None,
    ) -> bool:
        relative = _normalize_relative_path(path, self.root)
        if relative == ".":
            return False

        parts = [part for part in PurePosixPath(relative).parts if part not in {"."}]
        if not include_hidden and any(part.startswith(".") for part in parts):
            return True

        return any(_glob_matches(relative, pattern) for pattern in self._exclude_globs(extra_excludes))

    def _relative_arg(self, path: Path) -> str:
        relative = _normalize_relative_path(path, self.root)
        return "." if relative == "." else relative

    def _run_rg(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                args,
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.rg_timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ripgrep (rg) is not installed or is not in PATH. Install it with `brew install ripgrep`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"ripgrep timed out after {self.rg_timeout_seconds:.1f}s while scanning the server tree."
            ) from exc

        if completed.returncode not in {0, 1}:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown ripgrep failure"
            raise RuntimeError(detail)
        return completed

    def summarize_server_layout(
        self,
        *,
        relative_path: str = ".",
        max_depth: int = 2,
        max_entries_per_dir: int = 30,
        include_hidden: bool = False,
        extra_excludes: list[str] | None = None,
    ) -> dict[str, Any]:
        root = self.resolve_path(relative_path)
        max_depth = max(0, min(max_depth, 6))
        max_entries_per_dir = max(1, min(max_entries_per_dir, 200))

        def build_tree(path: Path, depth: int) -> dict[str, Any]:
            item: dict[str, Any] = {
                "path": _normalize_relative_path(path, self.root),
                "type": "directory" if path.is_dir() else "file",
            }
            if not path.is_dir():
                item["size_bytes"] = path.stat().st_size
                return item

            if depth >= max_depth:
                item["children"] = []
                item["truncated"] = True
                return item

            children: list[dict[str, Any]] = []
            entries = sorted(
                path.iterdir(),
                key=lambda candidate: (candidate.is_file(), candidate.name.lower()),
            )
            truncated = False
            for entry in entries:
                if self._is_excluded(
                    entry,
                    include_hidden=include_hidden,
                    extra_excludes=extra_excludes,
                ):
                    continue
                if len(children) >= max_entries_per_dir:
                    truncated = True
                    break

                child: dict[str, Any] = {
                    "path": _normalize_relative_path(entry, self.root),
                    "type": "directory" if entry.is_dir() else "file",
                    "symlink": entry.is_symlink(),
                }
                if entry.is_symlink():
                    try:
                        resolved = entry.resolve()
                        child["resolves_to"] = str(resolved)
                        child["outside_root"] = resolved != self.root and self.root not in resolved.parents
                    except OSError as exc:
                        child["symlink_error"] = str(exc)

                if entry.is_dir() and not entry.is_symlink():
                    child.update(build_tree(entry, depth + 1))
                else:
                    try:
                        child["size_bytes"] = entry.stat().st_size
                    except OSError:
                        pass
                children.append(child)

            item["children"] = children
            if truncated:
                item["truncated"] = True
            return item

        return {
            "root": str(self.root),
            "path": _normalize_relative_path(root, self.root),
            "max_depth": max_depth,
            "max_entries_per_dir": max_entries_per_dir,
            "exclude_globs": self._exclude_globs(extra_excludes),
            "tree": build_tree(root, 0),
        }

    def find_recent_logs(self, *, max_results: int = 10) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        max_results = max(1, min(max_results, 100))

        for relative in ("logs", "crash-reports", "kubejs", "scripts"):
            directory = self.root / relative
            if not directory.exists() or not directory.is_dir():
                continue
            for path in directory.rglob("*"):
                if not path.is_file():
                    continue
                if self._is_excluded(path, include_hidden=False):
                    continue
                candidates.append(
                    {
                        "path": _normalize_relative_path(path, self.root),
                        "size_bytes": path.stat().st_size,
                        "modified_at": _utc_timestamp(path.stat().st_mtime),
                        "modified_epoch": path.stat().st_mtime,
                    }
                )

        candidates.sort(key=lambda item: item["modified_epoch"], reverse=True)
        trimmed = candidates[:max_results]
        for item in trimmed:
            item.pop("modified_epoch", None)
        return {
            "root": str(self.root),
            "files": trimmed,
            "truncated": len(candidates) > max_results,
        }

    def list_files(
        self,
        *,
        relative_path: str = ".",
        globs: list[str] | None = None,
        include_hidden: bool = False,
        extra_excludes: list[str] | None = None,
        max_results: int = 200,
    ) -> dict[str, Any]:
        target = self.resolve_path(relative_path)
        max_results = max(1, min(max_results, 2000))

        args = ["rg", "--files", "--color", "never"]
        if include_hidden:
            args.append("--hidden")
        for pattern in globs or []:
            cleaned = str(pattern or "").strip()
            if cleaned:
                args.extend(["-g", cleaned])
        for pattern in self._exclude_globs(extra_excludes):
            args.extend(["-g", f"!{pattern}"])
        args.append(self._relative_arg(target))

        completed = self._run_rg(args)
        files = [line for line in completed.stdout.splitlines() if line]
        return {
            "path": _normalize_relative_path(target, self.root),
            "files": files[:max_results],
            "truncated": len(files) > max_results,
        }

    def search_text(
        self,
        *,
        pattern: str,
        relative_path: str = ".",
        fixed_strings: bool = False,
        case_sensitive: bool | None = None,
        context_lines: int = 2,
        max_results: int = 200,
        include_hidden: bool = False,
        globs: list[str] | None = None,
        extra_excludes: list[str] | None = None,
    ) -> dict[str, Any]:
        if not pattern.strip():
            raise ValueError("pattern is required")

        target = self.resolve_path(relative_path)
        context_lines = max(0, min(context_lines, 20))
        max_results = max(1, min(max_results, 500))

        args = ["rg", "--line-number", "--color", "never", "--max-count", str(max_results)]
        if context_lines:
            args.extend(["--context", str(context_lines)])
        if fixed_strings:
            args.append("--fixed-strings")
        if case_sensitive is True:
            args.append("--case-sensitive")
        elif case_sensitive is False:
            args.append("--ignore-case")
        if include_hidden:
            args.append("--hidden")
        for pattern_glob in globs or []:
            cleaned = str(pattern_glob or "").strip()
            if cleaned:
                args.extend(["-g", cleaned])
        for exclude_glob in self._exclude_globs(extra_excludes):
            args.extend(["-g", f"!{exclude_glob}"])
        args.extend([pattern, self._relative_arg(target)])

        completed = self._run_rg(args)
        output = completed.stdout.strip()
        lines = output.splitlines() if output else []
        preview = "\n".join(lines[:400])
        return {
            "path": _normalize_relative_path(target, self.root),
            "pattern": pattern,
            "matches_found": bool(lines),
            "output": preview or "No matches found.",
            "truncated": len(lines) > 400,
        }

    def compare_text_files(
        self,
        *,
        path_a: str,
        path_b: str,
        context_lines: int = 3,
        max_diff_lines: int = 400,
    ) -> dict[str, Any]:
        file_a = self.resolve_path(path_a)
        file_b = self.resolve_path(path_b)
        context_lines = max(0, min(context_lines, 20))
        max_diff_lines = max(20, min(max_diff_lines, 2000))

        lines_a = _read_text_file(file_a, max_bytes=self.max_text_bytes)
        lines_b = _read_text_file(file_b, max_bytes=self.max_text_bytes)
        diff = list(
            difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile=_normalize_relative_path(file_a, self.root),
                tofile=_normalize_relative_path(file_b, self.root),
                lineterm="",
                n=context_lines,
            )
        )
        preview = "\n".join(diff[:max_diff_lines])
        return {
            "path_a": _normalize_relative_path(file_a, self.root),
            "path_b": _normalize_relative_path(file_b, self.root),
            "identical": not diff,
            "diff": preview,
            "truncated": len(diff) > max_diff_lines,
        }

    def list_mod_jars(self, *, max_results: int = 300) -> dict[str, Any]:
        mods_dir = self.root / "mods"
        if not mods_dir.exists():
            return {"mods_dir": "mods", "files": [], "missing": True}

        max_results = max(1, min(max_results, 2000))
        files = []
        for path in sorted(mods_dir.glob("*.jar"), key=lambda candidate: candidate.name.lower()):
            files.append(
                {
                    "path": _normalize_relative_path(path, self.root),
                    "size_bytes": path.stat().st_size,
                    "modified_at": _utc_timestamp(path.stat().st_mtime),
                }
            )
        return {
            "mods_dir": "mods",
            "files": files[:max_results],
            "truncated": len(files) > max_results,
        }

    def detect_duplicate_mods(self, *, max_results: int = 50) -> dict[str, Any]:
        listing = self.list_mod_jars(max_results=5000)
        groups: dict[str, list[str]] = {}
        for item in listing.get("files", []):
            path_text = str(item["path"])
            stem = Path(path_text).stem.lower()
            normalized = VERSION_SUFFIX_RE.sub("", stem).strip("-_+")
            groups.setdefault(normalized or stem, []).append(path_text)

        duplicates = [
            {"normalized_name": name, "paths": sorted(paths)}
            for name, paths in groups.items()
            if len(paths) > 1
        ]
        duplicates.sort(key=lambda item: (len(item["paths"]) * -1, item["normalized_name"]))
        max_results = max(1, min(max_results, 200))
        return {
            "duplicates": duplicates[:max_results],
            "truncated": len(duplicates) > max_results,
        }
