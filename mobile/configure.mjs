// Prepares the Android app: bundles the phone inbox page (templates/mobile.html) into www/ and writes
// capacitor.config.json. The app has no server address built in: on first launch it asks for yours.
import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";

mkdirSync("www/static", { recursive: true });
copyFileSync("../templates/mobile.html", "www/index.html");
copyFileSync("../static/icon-192.png", "www/static/icon-192.png");
copyFileSync("../static/icon.svg", "www/static/icon.svg");

writeFileSync("capacitor.config.json", JSON.stringify({
  appId: "app.jobpilot.inbox",
  appName: "JobPilot",
  webDir: "www",
  server: { androidScheme: "https" },
  android: { backgroundColor: "#0f1115" },
  plugins: {
    BackgroundRunner: { label: "app.jobpilot.inbox.check", src: "runner.js", event: "checkJobs",
                        repeat: true, interval: 15, autoStart: true }
  }
}, null, 2));
console.log("www/ and capacitor.config.json ready");
