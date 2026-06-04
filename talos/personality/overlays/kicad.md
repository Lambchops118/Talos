# KiCad Domain Overlay

- Verify the live KiCad backend state before board-editing work when that context is available.
- If the user expects visible real-time board updates, prefer checking the KiCad UI and IPC state before saying placement is visible.
- If components come from the schematic, make sure the schematic has been synced to the board before placement or routing.
- For simple power rails in KiCad schematics, prefer canonical symbols such as `power:+5V` and `power:GND` rather than inventing generic voltage-source symbols.
- Use symbol-library discovery tools before guessing exact component identifiers.
