// After `npx cap add android`: wire up the Background Runner plugin (its JS engine .aar + notification permission).
import { readFileSync, writeFileSync } from "node:fs";
const gradle = "android/app/build.gradle";
let g = readFileSync(gradle, "utf8");
if (!g.includes("background-runner")) {
  g = g.replace("dirs '../capacitor-cordova-android-plugins/src/main/libs', 'libs'",
    "dirs '../capacitor-cordova-android-plugins/src/main/libs', 'libs'\n        dirs '../../node_modules/@capacitor/background-runner/android/src/main/libs', 'libs'");
  if (!g.includes("background-runner")) { console.error("build.gradle flatDir not found"); process.exit(1); }
  writeFileSync(gradle, g);
}
const manifest = "android/app/src/main/AndroidManifest.xml";
let m = readFileSync(manifest, "utf8");
if (!m.includes("POST_NOTIFICATIONS")) {
  m = m.replace("</manifest>", '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n</manifest>');
  writeFileSync(manifest, m);
}
console.log("android patched for background runner");
