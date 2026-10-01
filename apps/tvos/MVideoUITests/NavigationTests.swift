import XCTest

final class NavigationTests: XCTestCase {
    func testAutomaticallyMatchedArtistPhotosAndTiles() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["MVIDEO_TEST_ARTIST"] = "10,000 Maniacs"
        app.launch()
        try XCTSkipIf(app.textFields["server-origin"].waitForExistence(timeout: 3), "Pair the simulator with the real library.")
        XCTAssertTrue(app.buttons["artist-photo-0"].waitForExistence(timeout: 60))
        saveScreenshot(app, name: "Automatically matched artist page")
        app.terminate()
        app.launchEnvironment.removeValue(forKey: "MVIDEO_TEST_ARTIST")
        app.launch()
        XCTAssertTrue(app.buttons["nav-home"].waitForExistence(timeout: 10))
        let remote = XCUIRemote.shared
        remote.press(.right); remote.press(.right); remote.press(.select)
        XCTAssertTrue(app.staticTexts["The artists you love."].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["fanart.tv"].firstMatch.waitForExistence(timeout: 60))
        saveScreenshot(app, name: "Artist grid upgrades to fanart.tv photography")
    }
    func testArtistPhotosAreReachableAndReturnFocus() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["MVIDEO_TEST_ARTIST"] = "a-ha"
        app.launch()
        try XCTSkipIf(app.textFields["server-origin"].waitForExistence(timeout: 3), "Pair the simulator with the real library.")
        XCTAssertTrue(app.buttons["artist-photo-0"].waitForExistence(timeout: 30))
        let remote = XCUIRemote.shared
        for _ in 0..<40 {
            if app.buttons.matching(NSPredicate(format: "hasFocus == true AND identifier BEGINSWITH 'artist-photo-'")).firstMatch.exists { break }
            remote.press(.down)
        }
        let focused = app.buttons.matching(NSPredicate(format: "hasFocus == true AND identifier BEGINSWITH 'artist-photo-'")).firstMatch
        XCTAssertTrue(focused.exists, app.debugDescription)
        let identifier = focused.identifier
        let heading = app.staticTexts["artist-photos-heading"]
        XCTAssertGreaterThanOrEqual(focused.frame.minY, heading.frame.maxY)
        let lastVideo = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'video-'")).allElementsBoundByIndex.map(\.frame.maxY).max() ?? 0
        XCTAssertGreaterThan(heading.frame.minY, lastVideo + 20)
        let photos = XCTAttachment(screenshot: app.screenshot()); photos.name = "Reachable artist photos with separated rows"; photos.lifetime = .keepAlways; add(photos)
        remote.press(.select)
        XCTAssertTrue(app.buttons["photo-close"].waitForExistence(timeout: 10))
        let position = app.staticTexts["photo-position"].label
        for _ in 0..<3 where !app.buttons["photo-next"].hasFocus { remote.press(.right) }
        XCTAssertTrue(app.buttons["photo-next"].hasFocus)
        remote.press(.select)
        XCTAssertNotEqual(app.staticTexts["photo-position"].label, position)
        saveScreenshot(app, name: "Full-screen artist photo")
        remote.press(.menu)
        XCTAssertTrue(app.buttons[identifier].waitForExistence(timeout: 5))
        expectation(for: NSPredicate(format: "hasFocus == true"), evaluatedWith: app.buttons[identifier])
        waitForExpectations(timeout: 5)
        remote.press(.right)
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "hasFocus == true AND identifier BEGINSWITH 'artist-photo-'")).firstMatch.exists)
        XCTAssertFalse(app.buttons[identifier].hasFocus)
    }
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
        saveScreenshot(app, name: "Artist image tiles")
        remote.press(.right); remote.press(.select)
        XCTAssertTrue(app.buttons["Videos with an unconfirmed year"].waitForExistence(timeout: 10))
        saveScreenshot(app, name: "Year image tiles")
        remote.press(.right); remote.press(.select)
        XCTAssertTrue(app.staticTexts["A lifetime of music."].waitForExistence(timeout: 10))
        saveScreenshot(app, name: "Decade image tiles")
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
    private func saveScreenshot(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
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
