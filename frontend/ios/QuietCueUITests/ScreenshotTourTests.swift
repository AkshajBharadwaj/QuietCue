import XCTest

/// Drives the app through every screen and saves PNGs to the directory named
/// by the `QUIETCUE_SHOT_DIR` environment variable. Used during development to
/// check the iOS screens against the Android app; skipped when the variable is
/// missing.
final class ScreenshotTourTests: XCTestCase {
    private var shotDir: String? { ProcessInfo.processInfo.environment["QUIETCUE_SHOT_DIR"] }

    override func setUpWithError() throws {
        continueAfterFailure = true
        try XCTSkipIf(shotDir == nil, "Set QUIETCUE_SHOT_DIR to run the screenshot tour")
    }

    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["QUIETCUE_HUB_HOST"] = ProcessInfo.processInfo.environment["QUIETCUE_HUB_HOST"] ?? "127.0.0.1"
        app.launchEnvironment["QUIETCUE_SKIP_NOTIFICATION_PROMPT"] = "1"
        app.launch()
        return app
    }

    private func snap(_ app: XCUIApplication, _ name: String) {
        guard let dir = shotDir else { return }
        let data = XCUIScreen.main.screenshot().pngRepresentation
        try? data.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
    }

    private func tab(_ app: XCUIApplication, _ label: String) {
        let button = app.buttons[label].firstMatch
        if button.waitForExistence(timeout: 5) { button.tap() }
        sleep(1)
    }

    func testTourAllScreens() {
        let app = launch()
        sleep(3)
        snap(app, "01-home-top")
        app.swipeUp(velocity: .slow)
        sleep(1)
        snap(app, "02-home-bottom")

        tab(app, "Profiles")
        snap(app, "03-profiles-top")
        app.swipeUp(velocity: .slow)
        sleep(1)
        snap(app, "04-profiles-bottom")
        let editActive = app.buttons["Edit active profile"].firstMatch
        if editActive.waitForExistence(timeout: 3) {
            editActive.tap()
            sleep(1)
            snap(app, "05-editor-top")
            app.swipeUp(velocity: .slow)
            sleep(1)
            snap(app, "06-editor-sounds")
            let expander = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Show '")).firstMatch
            if expander.waitForExistence(timeout: 3) {
                expander.tap()
                sleep(1)
                snap(app, "07-editor-rule-expanded")
            }
            app.swipeDown(velocity: .fast)
            let back = app.buttons["Go back"].firstMatch
            if back.waitForExistence(timeout: 3) { back.tap() }
            sleep(1)
        }
        app.swipeDown(velocity: .fast)
        let describe = app.buttons["Describe a situation"].firstMatch
        if describe.waitForExistence(timeout: 3) {
            describe.tap()
            sleep(1)
            snap(app, "08-profile-agent")
            app.buttons["Go back"].firstMatch.tap()
            sleep(1)
        }
        let enroll = app.buttons["Enroll a sound"].firstMatch
        if enroll.waitForExistence(timeout: 3) {
            enroll.tap()
            sleep(1)
            snap(app, "09-enroll-sound")
            app.buttons["Go back"].firstMatch.tap()
            sleep(1)
        }

        tab(app, "Places")
        snap(app, "10-places")
        let demoPlace = app.buttons["Create hackathon demo place"].firstMatch
        if demoPlace.waitForExistence(timeout: 3) {
            demoPlace.tap()
            sleep(1)
            snap(app, "11-places-demo")
            let arrival = app.buttons["Test arrival"].firstMatch
            if arrival.waitForExistence(timeout: 3) {
                arrival.tap()
                sleep(1)
                tab(app, "Home")
                snap(app, "12-home-suggestion")
            }
        }

        tab(app, "My context")
        snap(app, "13-memory-top")
        app.swipeUp(velocity: .slow)
        sleep(1)
        snap(app, "14-memory-bottom")
        app.swipeDown(velocity: .fast)
        let editSpeech = app.buttons["Edit speech settings"].firstMatch
        if editSpeech.waitForExistence(timeout: 3) {
            editSpeech.tap()
            sleep(1)
            snap(app, "15-speech-settings")
            app.buttons["Go back"].firstMatch.tap()
            sleep(1)
        }
        let editName = app.buttons["Edit your name"].firstMatch
        if editName.waitForExistence(timeout: 3) {
            editName.tap()
            sleep(1)
            snap(app, "16-identity")
            app.buttons["Go back"].firstMatch.tap()
            sleep(1)
        }
        let addPerson = app.buttons["Add a person"].firstMatch
        if addPerson.waitForExistence(timeout: 3) {
            addPerson.tap()
            sleep(1)
            snap(app, "17-person")
            app.buttons["Go back"].firstMatch.tap()
            sleep(1)
        }
    }
}
