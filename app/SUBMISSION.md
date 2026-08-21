# Sarvamula — App Store & Play Store Submission Guide

Everything needed to submit **v1.0 (no audio)**. Audio ships later as a routine update (see end).

---

## 0. Artifacts (already built & signed)

| Platform | File | Notes |
|---|---|---|
| iOS | `app/artifacts/Sarvamula-1.0.ipa` | Signed w/ Apple Distribution (Team P33954J97U), passed `-validate-for-store` |
| Android | `app/artifacts/Sarvamula-1.0-release.aab` | Signed w/ your upload keystore |

Screenshots — all five views (home, read, kannada, search, anu), no alpha channel:

**Apple App Store** (exact required sizes — use whichever iPhone size ASC asks for):
- iPhone 6.5″/6.7″ (**1242×2688**): `app/artifacts/screenshots/ios-iphone-6.5/`
- iPhone 6.9″ (1320×2868): `app/artifacts/screenshots/ios-iphone-6.9/`
- iPad 13″ (2064×2752): `app/artifacts/screenshots/ios-ipad-13/`

**Google Play** (Play caps aspect at 16:9 — the iPhone shots at 2.17:1 are TOO TALL for Play, so use these instead):
- Phone (1613×2868, ratio 1.78:1 = 16:9): `app/artifacts/screenshots/play-phone/`
- Tablet (2064×2752, ratio 1.33:1): `app/artifacts/screenshots/play-tablet/` — **use the same files for BOTH the 7-inch and 10-inch tablet slots** (each side ≥1080, within range).
- Feature graphic (1024×500): `app/artifacts/feature-graphic-1024x500.png`
- App icon (512×512): `app/artifacts/play-store-icon-512.png`

### ⚠️ Back up the Android upload key (do this now)
- Keystore: `app/android/sarvamula-upload.keystore`
- Password: `IX0PaVuf5yF/xX6uguY8TqwA` (also in `app/android/keystore.properties`)
- Store both in your password manager + an offsite copy. Losing them means you must reset the upload key via Play support.

---

## 1. App identity

| Field | Value |
|---|---|
| App name | **Sarvamula** |
| Bundle ID (iOS) / Application ID (Android) | `com.sarvamula.reader` |
| Version | `1.0` (build `1`) |
| Apple Team ID | `P33954J97U` |
| Privacy policy URL | https://sites.google.com/view/rigvaani-privacypolicy/policy-sarvamula |

---

## 2. Listing copy (paste as-is)

**Subtitle (iOS, ≤30 chars):**
`Madhvacharya's works, offline`

**Promotional text (iOS, ≤170 chars):**
```
The complete works of Sri Madhvacharya in your pocket: 38 texts, eight scripts, full Sanskrit search, and cross-work research tools. Fully offline.
```

**Description (iOS, ≤4000 chars):**
```
Sarvamula is a complete, offline reader of the Sarvamula-grantha — the entire body of works of Sri Madhvacharya (Anandatirtha), founder of the Dvaita (Tattvavada) school of Vedanta.

All 38 works in one app, organized by prasthana:

• Gita-prasthana — Gita-bhashya, Gita-tatparya
• Sutra-prasthana — Brahmasutra-bhashya, Anuvyakhyana, Nyaya-vivarana, Anubhashya
• Upanishad-prasthana — bhashyas on the principal Upanishads
• Prakarana works — Vishnu-tattva-vinirnaya, Tattva-viveka, Mayavada-khandana, Tattva-sankhyana and the rest
• Stotra, Itihasa, Purana and Acara works

FEATURES

• Eight scripts — read any text in Devanagari, Roman (IAST), Kannada, Telugu, Tamil, Malayalam, Bengali or Gujarati, and switch instantly.
• Verse-and-commentary layout — mula verses and Madhva's bhashya are clearly structured, with pramana (scriptural citation) blocks set apart.
• Powerful Sanskrit search — full-text search across all 38 works or scoped to a single grantha, with vowel-aware matching and highlighted results.
• Anusandhana research tools — a concept locator that shows everywhere Madhva treats a concept (taratamya, bheda, moksha, bimba-pratibimba and more) across the whole corpus, plus a citation index of the sources he quotes.
• Adjustable reading size and a clean, distraction-free interface.
• 100% offline — no account, no ads, no tracking, no internet needed. The entire corpus lives on your device.

Built for students, scholars, and devotees of the Madhva (Tattvavada) tradition.
```

**Google Play — Short description (≤80 chars):**
```
Madhvacharya's complete works — 38 texts, 8 scripts, offline reader
```

**Google Play — Full description (≤4000 chars):**
```
Sarvamula is a complete, offline reader of the Sarvamula-grantha — the entire body of works of Sri Madhvacharya (Anandatirtha), founder of the Dvaita (Tattvavada) school of Vedanta.

All 38 works in one app, organized by prasthana:

• Gita-prasthana — Gita-bhashya, Gita-tatparya
• Sutra-prasthana — Brahmasutra-bhashya, Anuvyakhyana, Nyaya-vivarana, Anubhashya
• Upanishad-prasthana — bhashyas on the principal Upanishads
• Prakarana works — Vishnu-tattva-vinirnaya, Tattva-viveka, Mayavada-khandana, Tattva-sankhyana and the rest
• Stotra, Itihasa, Purana and Acara works

FEATURES

• Eight scripts — read any text in Devanagari, Roman (IAST), Kannada, Telugu, Tamil, Malayalam, Bengali or Gujarati, and switch instantly.
• Verse-and-commentary layout — mula verses and Madhva's bhashya are clearly structured, with pramana (scriptural citation) blocks set apart.
• Powerful Sanskrit search — full-text search across all 38 works or scoped to a single grantha, with vowel-aware matching and highlighted results.
• Anusandhana research tools — a concept locator that shows everywhere Madhva treats a concept (taratamya, bheda, moksha, bimba-pratibimba and more) across the whole corpus, plus a citation index of the sources he quotes.
• Adjustable reading size and a clean, distraction-free interface.
• 100% offline — no account, no ads, no tracking, no internet needed. The entire corpus lives on your device.

Built for students, scholars, and devotees of the Madhva (Tattvavada) tradition.
```

**Keywords (iOS, ≤100 chars, comma-separated, no spaces):**
```
madhva,madhwa,dvaita,dwaita,tattvavada,vedanta,sanskrit,anandatirtha,gita,brahmasutra,upanishad
```

**Categories:**
- iOS: Primary **Reference**, Secondary **Education**
- Play: Category **Books & Reference**

**Release name (Play — internal only, not shown to users):**
```
1.0 (1) — Initial release
```

**Release notes / "What's new" (Play, ≤500 chars):**
```
Welcome to Sarvamula — the complete works of Sri Madhvacharya, fully offline.

• All 38 works, grouped by prasthana
• Read in 8 scripts: Devanagari, Roman, Kannada, Telugu, Tamil, Malayalam, Bengali, Gujarati
• Full Sanskrit search across the whole corpus or a single text
• Anusandhana research tools: concept locator + citation index
```

**iOS "What's New":** not applicable for v1.0 (Apple shows it only on updates). Use it from v1.1 onward,
e.g. for the audio update: `• Added audio: tap to play verses  • Fixes and refinements`.

---

## 3. Ratings & privacy answers

**Age rating:** iOS **4+** / Play **Everyone**. No objectionable content.
(If asked about "Infrequent/Mild references to religious themes" on Apple, that is fine and stays 4+.)

**iOS App Privacy ("Data Not Collected"):**
- Data collection: **No**. The app makes no network calls, has no accounts, no analytics, no third-party SDKs.
- Answer every data-type question as **not collected**.

**Play Data safety:**
- Does your app collect or share user data? **No.**
- Is data encrypted in transit? N/A (no data leaves the device).
- Users can request deletion? N/A (no data collected).

**Play Content rating questionnaire:** answer "No" to all violence/sexual/etc.; category → Everyone.

> The `INTERNET` permission is present (Android) but unused in v1 — it is reserved for the v1.1 audio update. It does not imply data collection; declare "no data collected" regardless.

---

## 4. Upload — iOS (App Store Connect)

1. **App Store Connect → Apps → +** → New App.
   - Platform iOS, Name **Sarvamula**, Primary language English, Bundle ID `com.sarvamula.reader` (select the one auto-registered during the build), SKU `sarvamula-reader`.
2. **Upload the build** — pick ONE:
   - **Transporter app** (simplest): open Transporter, sign in, drag `Sarvamula-1.0.ipa`, Deliver.
   - **Xcode Organizer**: Window → Organizer → Archives → the Sarvamula archive → Distribute App → App Store Connect → Upload.
   - **CLI**: `xcrun altool --upload-app -f app/artifacts/Sarvamula-1.0.ipa -t ios -u <apple-id> -p <app-specific-password>`
     (create an app-specific password at appleid.apple.com → Sign-In & Security).
3. Wait ~10–30 min for the build to finish "Processing" in App Store Connect.
4. Fill the listing (copy above), add screenshots from both folders, set the privacy policy URL, complete App Privacy = not collected.
5. Select the processed build → **Add for Review** → Submit.

## 5. Upload — Android (Play Console)

1. **Play Console → Create app** — name **Sarvamula**, app (not game), Free.
2. Complete **Dashboard** setup tasks: Privacy policy URL, App access (all features available without restrictions), Ads = No ads, Content rating questionnaire, Target audience, Data safety = no data collected.
3. **Release → Production → Create release.**
   - You'll be prompted to enroll in **Play App Signing** (accept — Google manages the app key; your keystore is the *upload* key).
   - Upload `Sarvamula-1.0-release.aab`.
   - **versionCode must be unique & increasing per upload.** Current build = **versionCode 2** (versionName 1.0).
     If Play says "version code N has already been used," bump `versionCode` in `app/android/app/build.gradle`
     to the next integer and rebuild (`cd android && JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew bundleRelease`).
     versionName ("1.0") is the public string and can stay the same across such rebuilds.
4. Add **store listing**: short + full description (copy above), app icon (Play pulls 512px from the bundle, or upload `app/assets/icon-only.png`), phone + tablet screenshots, feature graphic → `app/artifacts/feature-graphic-1024x500.png`.
5. Roll out to Production → submit for review.

---

## 6. Phased plan — audio in v1.1

v1 ships with no audio. Audio is added later without any re-architecture:
1. Pre-generate Sanskrit TTS audio files (on-device TTS is unsuitable for Sanskrit).
2. Host on Cloudflare R2 (same pattern as your other apps).
3. v1.1 adds a play button per verse/block that streams from R2 on demand — keeps the app binary small and lets audio coverage grow without app updates.
4. Bump version → `npm run sync` → rebuild → upload as an update. Reviews for updates are typically faster.

---

## 7. Rebuilding after any web change

The `web/` folder is the single source of truth. After editing it:
```
cd app
npm run sync          # copies web/ → www/ and into both native projects
# Android AAB:
cd android && JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew bundleRelease
# iOS: bump build number, then Archive in Xcode (or the xcodebuild archive/export commands)
```
