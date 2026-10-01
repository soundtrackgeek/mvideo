import XCTest

final class NavigationTests: XCTestCase {
    func testConnectedRemoteNavigationAndReturn() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launch()
        try XCTSkipUnless(app.buttons["nav-home"].waitForExistence(timeout: 10), "Pair the simulator with a running library for integration verification.")
        let remote = XCUIRemote.shared
        XCTAssertTrue(app.buttons["nav-home"].hasFocus)
        remote.press(.right)
        XCTAssertTrue(app.buttons["nav-search"].hasFocus)
        remote.press(.select)
        XCTAssertTrue(app.textFields["search-input"].waitForExistence(timeout: 10))
        remote.press(.down)
        XCTAssertTrue(app.textFields["search-input"].hasFocus)
        remote.press(.select)
        XCTAssertTrue(app.buttons["done"].waitForExistence(timeout: 5))
        let keyboard = XCTAttachment(screenshot: app.screenshot()); keyboard.name = "Native search keyboard"; keyboard.lifetime = .keepAlways; add(keyboard)
        for _ in 0..<4 where !app.buttons["done"].hasFocus { remote.press(.down) }
        XCTAssertTrue(app.buttons["done"].hasFocus)
        remote.press(.select)
        XCTAssertTrue(app.buttons["done"].waitForNonExistence(timeout: 5))
        for _ in 0..<5 where !app.buttons["nav-search"].hasFocus { remote.press(.up) }
        XCTAssertTrue(app.buttons["nav-search"].hasFocus)
        remote.press(.right); remote.press(.select)
        XCTAssertTrue(app.staticTexts["The artists you love."].waitForExistence(timeout: 10))
        remote.press(.right); remote.press(.select)
        XCTAssertTrue(app.buttons["Videos with an unconfirmed year"].waitForExistence(timeout: 10))
        remote.press(.right); remote.press(.select)
        XCTAssertTrue(app.staticTexts["A lifetime of music."].waitForExistence(timeout: 10))
        for _ in 0..<4 { remote.press(.left) }
        remote.press(.select)
        XCTAssertTrue(app.buttons["shuffle"].waitForExistence(timeout: 10))
        remote.press(.down)
        for _ in 0..<5 {
            let focused = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
            if focused.identifier.hasPrefix("video-") { break }
            remote.press(.down)
        }
        let focused = app.buttons.matching(NSPredicate(format: "hasFocus == true")).firstMatch
        XCTAssertTrue(focused.identifier.hasPrefix("video-"), app.debugDescription)
        let identifier = focused.identifier
        let originalFrame = focused.frame
        remote.press(.select)
        XCTAssertTrue(app.otherElements["playback-screen"].waitForExistence(timeout: 30))
        let playback = XCTAttachment(screenshot: app.screenshot()); playback.name = "Real library playback"; playback.lifetime = .keepAlways; add(playback)
        remote.press(.menu)
        XCTAssertTrue(app.buttons[identifier].waitForExistence(timeout: 10))
        let restored = NSPredicate(format: "hasFocus == true")
        expectation(for: restored, evaluatedWith: app.buttons[identifier])
        waitForExpectations(timeout: 5)
        let samePosition = NSPredicate { _, _ in abs(app.buttons[identifier].frame.minY - originalFrame.minY) < 4 }
        expectation(for: samePosition, evaluatedWith: app.buttons[identifier])
        waitForExpectations(timeout: 5)
    }
    func testConnectionScreenRespondsToRemote() {
        let app = XCUIApplication(); app.launch()
        // Fresh installs show pairing; connected integration runs exercise the library instead.
        if app.textFields["server-origin"].waitForExistence(timeout: 8) {
            XCUIRemote.shared.press(.right)
            XCUIRemote.shared.press(.down)
            XCTAssertTrue(app.secureTextFields["pair-code"].exists)
            XCTAssertTrue(app.buttons["connect"].exists)
        } else {
            XCTAssertTrue(app.buttons["nav-home"].waitForExistence(timeout: 15))
            XCUIRemote.shared.press(.up)
            XCUIRemote.shared.press(.right)
            XCTAssertTrue(app.buttons["nav-search"].exists)
        }
    }
}
