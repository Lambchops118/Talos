from talos.backend.service import TalosBackend


def main() -> None:
    backend = TalosBackend().start()
    try:
        backend.wait_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()


if __name__ == "__main__":
    main()

