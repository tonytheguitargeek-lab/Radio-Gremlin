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
    var radioWindow: NSWindow?
    var radioStatus: NSTextField?
    var radioBusy = false
    var originalBluetooth = false
    var originalHopLimit = 0
    var radioSnapshot: [String: Any] = [:]
    var regionCodes: [String: Int] = [:]
    var presetCodes: [String: Int] = [:]
    var radioDropdowns: [String: NSPopUpButton] = [:]
    var radioNeedsReload = false
    var applyButton: NSButton?
    var backupButton: NSButton?
    var radioSwitches: [String: NSSwitch] = [:]
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
            contentRect: NSRect(x: 0, y: 0, width: 390, height: 620),
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
        heading("MESH OPERATIONS CENTER / V1.1 DEV", size: 11)
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

        status("Radio Link", key: "radio")
        status("Recovery Watchdog", key: "watchdog")
        status("Sleep Prevention", key: "sleep")

        divider()

        buttons([
            ("Start All", "startAll"),
            ("Stop All", "stopAll")
        ])

        buttons([("Radio Configuration", "radioConfig")])

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
            let bot = self.alive("gremlin")
            let obs = self.alive("observatory")
            let watchdog = self.alive("watchdog")

            let radio = self.run(
                "cd \(self.quoted(self.gremlinDir.path)) && ./venv/bin/python -c " +
                "'import gremlin_settings as g; print(1 if g.current_radio_connected() else 0)'"
            ).trimmingCharacters(in: .whitespacesAndNewlines) == "1"
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






    @objc func applyRadioChanges(_ sender: NSButton) {
        guard !radioBusy, !radioNeedsReload,
              !alive("gremlin"), !alive("watchdog"),
              let bluetooth = radioSwitches["Bluetooth"],
              let hop = radioDropdowns["Hop limit"],
              let hopValue = Int(hop.titleOfSelectedItem ?? "")
        else { return }

        var changes: [String: Any] = [:]
        let expected = radioSnapshot
        var descriptions: [String] = []

        func stage(_ key: String, _ label: String,
                   _ value: Any, _ display: String) {
            guard let old = expected[key] else { return }

            if String(describing: old) != String(describing: value) {
                if let a = old as? NSNumber,
                   let b = value as? NSNumber,
                   a == b { return }

                changes[key] = value
                descriptions.append(label + ": " + display)
            }
        }

        let switches = [
            "Bluetooth": "bluetooth.enabled",
            "Wi-Fi": "network.wifi_enabled",
            "MQTT": "mqtt.enabled",
            "RF transmit": "lora.tx_enabled"
        ]

        for (label, key) in switches {
            guard let control = radioSwitches[label] else { return }
            let enabled = control.state == .on
            stage(key, label, enabled, enabled ? "ON" : "OFF")
        }

        guard let regionName = radioDropdowns["Region"]?
                  .titleOfSelectedItem,
              let region = regionCodes[regionName],
              let presetName = radioDropdowns["Modem preset"]?
                  .titleOfSelectedItem,
              let preset = presetCodes[presetName]
        else { return }

        stage("lora.region", "Region", region, regionName)

        if expected["lora.use_preset"] as? Bool == true {
            stage("lora.modem_preset", "Modem preset",
                  preset, presetName)
        }

        stage("lora.hop_limit", "Hop limit",
              hopValue, String(hopValue))

        var target = expected
        for (key, value) in changes {
            target[key] = value
        }

        let verifiedTarget = target

        guard !changes.isEmpty else {
            radioStatus?.stringValue = "● NO CHANGES"
            return
        }

        guard let d = try? JSONSerialization.data(
                  withJSONObject: changes),
              let e = try? JSONSerialization.data(
                  withJSONObject: expected),
              let desiredJSON = String(data: d, encoding: .utf8),
              let expectedJSON = String(data: e, encoding: .utf8)
        else { return }

        let alert = NSAlert()
        alert.messageText = "Apply Radio Configuration?"
        alert.informativeText =
            descriptions.joined(separator: "\n") +
            "\n\nA Quick Backup will be saved first." +
            "\nAllow approximately 60–90 seconds."

        if changes["network.wifi_enabled"] as? Bool == true {
            alert.informativeText +=
                "\n\nWi-Fi requires existing network credentials."
        }

        if changes["mqtt.enabled"] as? Bool == true {
            alert.informativeText +=
                "\n\nMQTT uses the radio's existing broker and channel settings."
        }

        if changes["lora.region"] != nil ||
           changes["lora.modem_preset"] != nil ||
           changes["lora.tx_enabled"] != nil {
            alert.informativeText +=
                "\n\nRF changes may interrupt mesh connectivity. Use only settings authorized for your location."
        }

        alert.addButton(withTitle: "Apply Changes")
        alert.addButton(withTitle: "Cancel")

        guard alert.runModal() == .alertFirstButtonReturn
        else { return }

        radioBusy = true
        sender.isEnabled = false
        backupButton?.isEnabled = false
        for control in radioSwitches.values {
            control.isEnabled = false
        }
        for control in radioDropdowns.values {
            control.isEnabled = false
        }

        radioWindow?.standardWindowButton(.closeButton)?
            .isEnabled = false

        radioStatus?.textColor = .systemOrange
        radioStatus?.stringValue = "● CONNECTING TO RADIO..."

        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            process.executableURL = self.gremlinDir
                .appendingPathComponent("venv/bin/python")
            process.currentDirectoryURL = self.gremlinDir
            process.arguments = [
                "gremlin_radio_config.py",
                "apply", desiredJSON, expectedJSON
            ]

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe

            var output = ""
            var pending = ""
            var success = false

            do {
                try process.run()

                while true {
                    let data = pipe.fileHandleForReading.availableData
                    if data.isEmpty { break }

                    let chunk = String(decoding: data, as: UTF8.self)
                    output += chunk
                    pending += chunk

                    while let newline = pending.firstIndex(of: "\n") {
                        let line = String(pending[..<newline])
                        pending = String(
                            pending[pending.index(after: newline)...])

                        if let range = line.range(of: "PROGRESS: ") {
                            let message = String(line[range.upperBound...])

                            DispatchQueue.main.async {
                                self.radioStatus?.stringValue =
                                    "● " + message
                            }
                        }
                    }
                }

                process.waitUntilExit()

                success = process.terminationStatus == 0 &&
                    output.components(separatedBy: .newlines)
                        .contains("WRITE_VERIFIED")
            } catch {
                success = false
            }

            let verified = success

            DispatchQueue.main.async {
                self.radioBusy = false
                self.backupButton?.isEnabled = true
                self.radioWindow?.standardWindowButton(.closeButton)?
                    .isEnabled = true

                if verified {
                    self.radioSnapshot = verifiedTarget
                    self.originalBluetooth = bluetooth.state == .on
                    self.originalHopLimit = hopValue

                    for control in self.radioSwitches.values {
                        control.isEnabled = true
                    }

                    for (name, control) in self.radioDropdowns {
                        control.isEnabled =
                            name != "Modem preset" ||
                            verifiedTarget["lora.use_preset"] as? Bool == true
                    }
                    sender.isEnabled = true

                    self.radioStatus?.textColor = self.green
                    self.radioStatus?.stringValue =
                        "● CONFIGURATION VERIFIED\nQuick Backup saved."
                } else {
                    self.radioNeedsReload = true
                    self.radioStatus?.textColor = .systemRed
                    self.radioStatus?.stringValue =
                        "● WRITE NOT VERIFIED\nClose and reopen Radio Config."
                }
            }
        }
    }


    @objc func backupRadio(_ sender: NSButton) {

        guard !radioBusy else { return }

        guard !alive("gremlin"), !alive("watchdog") else {
            radioStatus?.stringValue = "● RADIO BUSY"
            radioStatus?.textColor = .systemOrange
            return
        }

        radioBusy = true
        applyButton?.isEnabled = false
        sender.isEnabled = false
        sender.title = "Backing Up..."

        radioWindow?.standardWindowButton(.closeButton)?
            .isEnabled = false

        for control in radioSwitches.values {
            control.isEnabled = false
        }

        for control in radioDropdowns.values {
            control.isEnabled = false
        }

        radioStatus?.stringValue = "● STARTING FULL BACKUP..."
        radioStatus?.textColor = .systemOrange

        DispatchQueue.global(qos: .userInitiated).async {

            let process = Process()
            process.executableURL = self.gremlinDir
                .appendingPathComponent("venv/bin/python")

            process.currentDirectoryURL = self.gremlinDir
            process.arguments = [
                "gremlin_radio_config.py", "full-backup"
            ]

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe

            var pending = ""
            var output = ""
            var success = false

            do {
                try process.run()

                while true {
                    let data = pipe.fileHandleForReading.availableData
                    if data.isEmpty { break }

                    let chunk = String(decoding: data, as: UTF8.self)
                    output += chunk
                    pending += chunk

                    while let newline = pending.firstIndex(of: "\n") {
                        let line = String(pending[..<newline])
                        pending = String(
                            pending[pending.index(after: newline)...])

                        if let range = line.range(of: "PROGRESS: ") {
                            let message = String(line[range.upperBound...])

                            DispatchQueue.main.async {
                                self.radioStatus?.stringValue =
                                    "● " + message
                            }
                        }
                    }
                }

                process.waitUntilExit()

                success = process.terminationStatus == 0 &&
                    output.contains("BACKUP_OK")

            } catch {
                success = false
            }

            let completed = success

            DispatchQueue.main.async {

                self.radioBusy = false
                sender.isEnabled = true
                sender.title = "Backup Config"

                self.radioWindow?.standardWindowButton(.closeButton)?
                    .isEnabled = true

                self.applyButton?.isEnabled = !self.radioNeedsReload

                if !self.radioNeedsReload {
                    for control in self.radioSwitches.values {
                        control.isEnabled = true
                    }

                    for (name, control) in self.radioDropdowns {
                        control.isEnabled =
                            name != "Modem preset" ||
                            self.radioSnapshot["lora.use_preset"] as? Bool == true
                    }
                }

                if completed {
                    self.radioStatus?.stringValue =
                        "● FULL BACKUP SUCCESSFUL\nSaved to ~/RadioBackups/"
                    self.radioStatus?.textColor = self.green
                } else {
                    self.radioStatus?.stringValue =
                        "● BACKUP FAILED\nCheck radio connection and retry."
                    self.radioStatus?.textColor = .systemRed
                }
            }
        }
    }

    func presentRadioSettings(_ readings: String) {
        var values: [String: String] = [:]

        for line in readings.components(separatedBy: .newlines) {
            let parts = line.split(separator: ":", maxSplits: 1)
            if parts.count == 2 {
                values[String(parts[0])] =
                    String(parts[1]).trimmingCharacters(in: .whitespaces)
            }
        }

        func decode(_ key: String) -> [String: Any]? {
            guard let data = values[key]?.data(using: .utf8)
            else { return nil }
            return (try? JSONSerialization.jsonObject(
                with: data)) as? [String: Any]
        }

        guard let snapshot = decode("Snapshot"),
              snapshot.count == 9,
              let regions = decode("RegionCodes") as? [String: Int],
              let presets = decode("PresetCodes") as? [String: Int]
        else {
            let alert = NSAlert()
            alert.messageText = "Incomplete radio configuration"
            alert.informativeText = "No configuration changes permitted."
            alert.runModal()
            return
        }

        radioSnapshot = snapshot
        regionCodes = regions
        presetCodes = presets

        let panel = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 430, height: 680),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )

        panel.title = "Gremlin Radio Configuration"
        panel.appearance = NSAppearance(named: .darkAqua)
        panel.isReleasedWhenClosed = false
        radioWindow = panel

        let content = NSView()
        content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(
            red: 0.065, green: 0.085,
            blue: 0.11, alpha: 1
        ).cgColor
        panel.contentView = content

        let form = NSStackView()
        form.orientation = .vertical
        form.alignment = .leading
        form.spacing = 12
        form.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(form)

        NSLayoutConstraint.activate([
            form.topAnchor.constraint(
                equalTo: content.topAnchor, constant: 22),
            form.leadingAnchor.constraint(
                equalTo: content.leadingAnchor, constant: 22),
            form.trailingAnchor.constraint(
                equalTo: content.trailingAnchor, constant: -22)
        ])

        let header = NSTextField(labelWithString: "RADIO CONFIG")
        header.font = .monospacedSystemFont(
            ofSize: 24, weight: .medium)
        header.textColor = green
        form.addArrangedSubview(header)

        let subtitle = NSTextField(labelWithString:
            "GREMLIN / RADIO MANAGEMENT")
        subtitle.font = .monospacedSystemFont(
            ofSize: 11, weight: .medium)
        subtitle.textColor = green
        form.addArrangedSubview(subtitle)

        func separator() {
            let line = NSBox()
            line.boxType = .separator
            form.addArrangedSubview(line)
            line.widthAnchor.constraint(
                equalTo: form.widthAnchor).isActive = true
        }

        separator()

        let connected = NSTextField(labelWithString:
            "● USB CONFIGURATION LOADED")
        connected.font = .monospacedSystemFont(
            ofSize: 11, weight: .semibold)
        connected.textColor = green
        form.addArrangedSubview(connected)

        separator()

        func section(_ title: String) {
            let label = NSTextField(labelWithString: title)
            label.font = .monospacedSystemFont(ofSize: 12, weight: .bold)
            label.textColor = green
            form.addArrangedSubview(label)
        }

        func field(_ name: String, _ control: NSView) {
            let row = NSStackView()
            row.orientation = .horizontal
            row.spacing = 12

            let label = NSTextField(labelWithString: name)
            label.widthAnchor.constraint(equalToConstant: 125).isActive = true

            row.addArrangedSubview(label)
            row.addArrangedSubview(control)
            form.addArrangedSubview(row)
        }

        radioSwitches.removeAll()
        radioDropdowns.removeAll()
        radioNeedsReload = false
        originalHopLimit = Int(values["Hop limit"] ?? "") ?? 0
        originalBluetooth = values["Bluetooth"] == "ENABLED"

        func toggle(_ name: String) {
            let control = NSSwitch()
            control.state = values[name] == "ENABLED" ? .on : .off
            control.identifier = NSUserInterfaceItemIdentifier(name)
            control.target = self
            control.action = #selector(radioToggleChanged(_:))
            radioSwitches[name] = control
            control.isEnabled = true
            field(name, control)
        }

        func dropdown(_ name: String, _ choices: [String]) {
            let control = NSPopUpButton(frame: .zero, pullsDown: false)
            control.addItems(withTitles: choices)
            control.isEnabled =
                name != "Modem preset" ||
                values["Use preset"] == "ENABLED"
            radioDropdowns[name] = control
            if let current = values[name] {
                if !choices.contains(current) {
                    control.addItem(withTitle: current)
                }
                control.selectItem(withTitle: current)
            }
            control.widthAnchor.constraint(equalToConstant: 210).isActive = true
            field(name, control)
        }

        section("CONNECTIVITY")
        toggle("Bluetooth")
        toggle("Wi-Fi")
        toggle("MQTT")

        separator()
        section("RF CONFIGURATION")

        dropdown("Region", regionCodes
            .filter { $0.value != 0 }
            .sorted { $0.value < $1.value }
            .map { $0.key })

        dropdown("Modem preset", presetCodes
            .sorted { $0.value < $1.value }
            .map { $0.key })

        let power = NSTextField(string:
            (values["TX power"] ?? "").replacingOccurrences(
                of: " dBm", with: ""))
        power.widthAnchor.constraint(equalToConstant: 100).isActive = true
        power.isEnabled = false
        field("TX power (dBm)", power)

        dropdown("Hop limit", (0...7).map { String($0) })
        toggle("RF transmit")

        let note = NSTextField(labelWithString:
            "DEV TEST — TX power is read-only.")
        note.font = .systemFont(ofSize: 11)
        note.textColor = .secondaryLabelColor
        form.addArrangedSubview(note)

        separator()

        let actions = NSStackView()
        actions.orientation = .horizontal
        actions.distribution = .fillEqually
        actions.spacing = 8

        let close = NSButton(
            title: "Close",
            target: self,
            action: #selector(closeRadioWindow(_:)))
        close.bezelStyle = .rounded

        let apply = NSButton(
            title: "Apply Changes",
            target: self,
            action: #selector(applyRadioChanges(_:)))
        apply.bezelStyle = .rounded
        apply.isEnabled = true
        applyButton = apply

        let backup = NSButton(
            title: "Backup Config",
            target: self,
            action: #selector(backupRadio(_:)))
        backup.bezelStyle = .rounded
        backupButton = backup

        actions.addArrangedSubview(backup)
        actions.addArrangedSubview(close)
        actions.addArrangedSubview(apply)
        form.addArrangedSubview(actions)

        actions.widthAnchor.constraint(
            equalTo: form.widthAnchor).isActive = true
        actions.heightAnchor.constraint(
            equalToConstant: 30).isActive = true

        separator()

        let status = NSTextField(wrappingLabelWithString:
            "● READY — Configuration loaded")
        status.font = .monospacedSystemFont(
            ofSize: 11, weight: .medium)
        status.textColor = green
        status.maximumNumberOfLines = 4

        form.addArrangedSubview(status)
        status.widthAnchor.constraint(
            equalTo: form.widthAnchor).isActive = true

        radioStatus = status

        panel.center()
        panel.makeKeyAndOrderFront(nil)
    }

    @objc func closeRadioWindow(_ sender: NSButton) {
        guard !radioBusy else {
            radioStatus?.stringValue = "● WAIT — Radio operation in progress"
            radioStatus?.textColor = .systemOrange
            return
        }
        radioWindow?.close()
    }

    @objc func radioToggleChanged(_ sender: NSSwitch) {
        guard sender.state == .on else { return }

        switch sender.identifier?.rawValue {
        case "Bluetooth":
            radioSwitches["Wi-Fi"]?.state = .off
        case "Wi-Fi":
            radioSwitches["Bluetooth"]?.state = .off
        default:
            break
        }
    }

    func applicationShouldTerminate(
        _ sender: NSApplication
    ) -> NSApplication.TerminateReply {
        return radioBusy ? .terminateCancel : .terminateNow
    }


    func showRadioConfiguration() {
        guard !radioBusy else { return }

        if let existing = radioWindow, existing.isVisible {
            existing.makeKeyAndOrderFront(nil)
            return
        }

        guard !alive("gremlin"), !alive("watchdog") else {
            let alert = NSAlert()
            alert.messageText = "Radio is busy"
            alert.informativeText = "Stop Gremlin and the watchdog first."
            alert.runModal()
            return
        }

        radioBusy = true

        let script = """
        import json
        import gremlin_radio_config as rc
        from meshtastic.protobuf import config_pb2

        radio = rc.connect()

        try:
            values = rc.read_settings(radio)
        finally:
            radio.close()

        enums = config_pb2.Config.LoRaConfig

        fields = [
            ("Bluetooth", "bluetooth.enabled"),
            ("Wi-Fi", "network.wifi_enabled"),
            ("MQTT", "mqtt.enabled"),
            ("Region", "lora.region"),
            ("Modem preset", "lora.modem_preset"),
            ("TX power", "lora.tx_power"),
            ("Hop limit", "lora.hop_limit"),
            ("RF transmit", "lora.tx_enabled"),
            ("Use preset", "lora.use_preset")
        ]

        snapshot = json.dumps(values)
        regions = json.dumps(dict(enums.RegionCode.items()))
        presets = json.dumps(dict(enums.ModemPreset.items()))

        values["lora.region"] = enums.RegionCode.Name(
            values["lora.region"])

        values["lora.modem_preset"] = enums.ModemPreset.Name(
            values["lora.modem_preset"])

        print("RADIO_OK")
        print("Snapshot: " + snapshot)
        print("RegionCodes: " + regions)
        print("PresetCodes: " + presets)

        for label, key in fields:
            value = values[key]

            if type(value) is bool:
                value = "ENABLED" if value else "DISABLED"

            if key == "lora.tx_power":
                value = str(value) + " dBm"

            print(label + ": " + str(value))
        """

        let command =
            "cd " + quoted(gremlinDir.path) +
            " && ./venv/bin/python -c " +
            quoted(script) + " 2>&1"

        let loading = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 360, height: 140),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )

        loading.title = "Gremlin Radio Configuration"
        loading.appearance = NSAppearance(named: .darkAqua)
        loading.isReleasedWhenClosed = false

        let spinner = NSProgressIndicator(
            frame: NSRect(x: 164, y: 75, width: 32, height: 32)
        )
        spinner.style = .spinning
        spinner.startAnimation(nil)

        let label = NSTextField(labelWithString:
            "READING USB CONFIGURATION...")
        label.frame = NSRect(x: 20, y: 35, width: 320, height: 22)
        label.alignment = .center
        label.font = .monospacedSystemFont(ofSize: 12, weight: .medium)
        label.textColor = green

        loading.contentView?.addSubview(spinner)
        loading.contentView?.addSubview(label)

        radioWindow = loading
        loading.center()
        loading.makeKeyAndOrderFront(nil)

        DispatchQueue.global(qos: .userInitiated).async {
            let result = self.run(command)

            DispatchQueue.main.async {
                spinner.stopAnimation(nil)
                loading.close()
                self.radioWindow = nil
                self.radioBusy = false

                if let range = result.range(of: "RADIO_OK\n") {
                    let readings = String(result[range.upperBound...])
                    self.presentRadioSettings(readings)
                } else {
                    let alert = NSAlert()
                    alert.messageText = "Radio Configuration Error"
                    alert.informativeText = result.isEmpty
                        ? "No response from radio."
                        : result
                    alert.addButton(withTitle: "Close")
                    alert.runModal()
                }
            }
        }
    }

    @objc func clicked(_ sender: NSButton) {
        if sender.identifier?.rawValue == "startGremlin" ||
           sender.identifier?.rawValue == "startAll" {
            if radioBusy || radioWindow?.isVisible == true {
                radioWindow?.makeKeyAndOrderFront(nil)
                radioStatus?.stringValue =
                    "● Close Radio Config before starting Gremlin"
                radioStatus?.textColor = .systemOrange
                return
            }
        }
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
        case "radioConfig":
            showRadioConfiguration()
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
