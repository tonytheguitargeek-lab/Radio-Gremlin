// Gremlin Control Center V1.0 — part of Radio Gremlin (optional, macOS only)
// Copyright (C) 2026 Bad Audio Guy
// SPDX-License-Identifier: GPL-3.0-only
//
// One window to start/stop Radio Gremlin and Mesh Observatory, open the Observatory, view the
// Gremlin log, and see the radio link, watchdog and sleep-prevention status. Status is read from this
// installation's pid files; buttons run the scripts in <install dir>/scripts. Build with
// macos/install-macos-apps.sh.
//
// This program is free software: you can redistribute it and/or modify it under the terms of the GNU
// General Public License version 3. It is distributed WITHOUT ANY WARRANTY. See LICENSE.

import Cocoa

class ControlCenter: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var timer: Timer?
    var indicators: [String: NSTextField] = [:]
    var stack: NSStackView!

    // Install directory (the folder containing meshing-around/ and scripts/), written into the app's
    // Info.plist by install-macos-apps.sh. Falls back to ~/RadioGremlin.
    let root: URL = {
        if let dir = Bundle.main.object(forInfoDictionaryKey: "RadioGremlinDir") as? String, !dir.isEmpty {
            return URL(fileURLWithPath: (dir as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("RadioGremlin")
    }()
    var gremlinDir: URL { root.appendingPathComponent("meshing-around") }
    var radioAddress = ""   // "host:port", read once from the Radio Gremlin settings

    let green = NSColor(
        red: 0.32, green: 0.87,
        blue: 0.58, alpha: 1
    )

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 390, height: 570),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )

        window.title = "Gremlin Control Center"
        window.appearance = NSAppearance(named: .darkAqua)
        window.isReleasedWhenClosed = false

        stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false

        let content = NSView()
        content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(
            red: 0.065, green: 0.085,
            blue: 0.11, alpha: 1
        ).cgColor

        content.addSubview(stack)
        window.contentView = content

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(
                equalTo: content.topAnchor, constant: 22),
            stack.leadingAnchor.constraint(
                equalTo: content.leadingAnchor, constant: 22),
            stack.trailingAnchor.constraint(
                equalTo: content.trailingAnchor, constant: -22)
        ])

        heading("GREMLIN CONTROL", size: 24)
        heading("MESH OPERATIONS CENTER / V1.0", size: 11)
        divider()

        status("Radio Gremlin", key: "gremlin")
        buttons([
            ("Start Gremlin", "startGremlin"),
            ("Stop Gremlin", "stopGremlin")
        ])
        buttons([("View Gremlin Log", "log")])

        divider()

        status("Mesh Observatory", key: "observatory")
        buttons([
            ("Start Observatory", "startObservatory"),
            ("Stop Observatory", "stopObservatory")
        ])
        buttons([("Open Observatory", "openObservatory")])

        divider()

        status("Radio TCP", key: "radio")
        status("Recovery Watchdog", key: "watchdog")
        status("Sleep Prevention", key: "sleep")

        divider()

        buttons([
            ("Start All", "startAll"),
            ("Stop All", "stopAll")
        ])

        heading("Closing this window leaves services running.", size: 10)

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        refresh()

        timer = Timer.scheduledTimer(
            withTimeInterval: 3,
            repeats: true
        ) { [weak self] _ in
            self?.refresh()
        }
    }

    func heading(_ text: String, size: CGFloat) {
        let label = NSTextField(labelWithString: text)
        label.font = .monospacedSystemFont(
            ofSize: size, weight: .medium
        )
        label.textColor = green
        stack.addArrangedSubview(label)
    }

    func divider() {
        let line = NSBox()
        line.boxType = .separator
        stack.addArrangedSubview(line)
        line.widthAnchor.constraint(
            equalTo: stack.widthAnchor
        ).isActive = true
    }

    func status(_ name: String, key: String) {
        let row = NSStackView()
        row.orientation = .horizontal

        let label = NSTextField(labelWithString: name)
        label.font = .systemFont(ofSize: 13, weight: .medium)

        let indicator = NSTextField(labelWithString: "CHECKING")
        indicator.font = .monospacedSystemFont(
            ofSize: 11, weight: .semibold
        )
        indicator.alignment = .right

        label.setContentHuggingPriority(.defaultLow, for: .horizontal)
        indicator.setContentHuggingPriority(.required, for: .horizontal)

        row.addArrangedSubview(label)
        row.addArrangedSubview(indicator)

        stack.addArrangedSubview(row)
        row.widthAnchor.constraint(
            equalTo: stack.widthAnchor
        ).isActive = true

        indicators[key] = indicator
    }

    func buttons(_ items: [(String, String)]) {
        let row = NSStackView()
        row.orientation = .horizontal
        row.distribution = .fillEqually
        row.spacing = 8

        for (title, command) in items {
            let button = NSButton(
                title: title,
                target: self,
                action: #selector(clicked(_:))
            )
            button.bezelStyle = .rounded
            button.identifier = NSUserInterfaceItemIdentifier(command)
            button.heightAnchor.constraint(
                equalToConstant: 30
            ).isActive = true
            row.addArrangedSubview(button)
        }

        stack.addArrangedSubview(row)
        row.widthAnchor.constraint(
            equalTo: stack.widthAnchor
        ).isActive = true
    }

    func run(_ command: String) -> String {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", command]
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return String(data: data, encoding: .utf8) ?? ""
        } catch {
            return ""
        }
    }

    func update(_ key: String, _ active: Bool, _ yes: String, _ no: String) {
        indicators[key]?.stringValue = active ? "● " + yes : "● " + no
        indicators[key]?.textColor = active ? green : .systemRed
    }

    func refresh() {
        DispatchQueue.global(qos: .utility).async {
            if self.radioAddress.isEmpty {
                self.radioAddress = self.run(
                    "cd \(self.quoted(self.gremlinDir.path)) && ./venv/bin/python -c " +
                    "'import gremlin_settings as g; s=g.load(); print(\"%s:%d\" % (s.radio_host, s.radio_port))'"
                ).trimmingCharacters(in: .whitespacesAndNewlines)
            }

            let bot = self.alive("gremlin")
            let obs = self.alive("observatory")
            let watchdog = self.alive("watchdog")

            let radio = !self.radioAddress.hasPrefix(":") && !self.radioAddress.isEmpty && !self.run(
                "lsof -nP -iTCP@\(self.radioAddress) -sTCP:ESTABLISHED"
            ).isEmpty

            let sleep = !self.run(
                "launchctl list | awk '$3 == \"com.radiogremlin.caffeinate\" && $1 ~ /^[0-9]+$/ {print $1}'"
            ).isEmpty

            DispatchQueue.main.async {
                self.update("gremlin", bot, "RUNNING", "STOPPED")
                self.update("observatory", obs, "RUNNING", "STOPPED")
                self.update("watchdog", watchdog, "ACTIVE", "OFF")
                self.update("radio", radio, "CONNECTED", "OFFLINE")
                self.update("sleep", sleep, "ACTIVE", "OFF")
            }
        }
    }

    func quoted(_ path: String) -> String {
        return "'" + path.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    // True if <meshing-around>/<name>.pid names a running process (this installation only)
    func alive(_ name: String) -> Bool {
        let pidFile = gremlinDir.appendingPathComponent(name + ".pid").path
        guard let text = try? String(contentsOfFile: pidFile, encoding: .utf8),
              let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)) else { return false }
        return kill(pid, 0) == 0
    }

    func launch(_ name: String) {
        let scripts = [
            "Start Gremlin": "start-gremlin.sh", "Stop Gremlin": "stop-gremlin.sh",
            "Gremlin Log": "view-log.sh",
            "Start Observatory": "start-observatory.sh", "Stop Observatory": "stop-observatory.sh",
            "Open Observatory": "open-observatory.sh"
        ]
        guard let script = scripts[name] else { return }
        let url = root.appendingPathComponent("scripts").appendingPathComponent(script)

        guard FileManager.default.fileExists(atPath: url.path) else {
            let alert = NSAlert()
            alert.messageText = "Radio Gremlin script not found"
            alert.informativeText = url.path
            alert.runModal()
            return
        }

        DispatchQueue.global(qos: .userInitiated).async {
            _ = self.run(self.quoted(url.path))
            DispatchQueue.main.async { self.refresh() }
        }
    }

    @objc func clicked(_ sender: NSButton) {
        switch sender.identifier?.rawValue {
        case "startGremlin": launch("Start Gremlin")
        case "stopGremlin": launch("Stop Gremlin")
        case "log": launch("Gremlin Log")
        case "startObservatory": launch("Start Observatory")
        case "stopObservatory": launch("Stop Observatory")
        case "openObservatory": launch("Open Observatory")
        case "startAll":
            launch("Start Gremlin")
            launch("Start Observatory")
        case "stopAll":
            launch("Stop Observatory")
            launch("Stop Gremlin")
        default: break
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(
        _ sender: NSApplication
    ) -> Bool {
        return true
    }
}

let app = NSApplication.shared
let delegate = ControlCenter()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
