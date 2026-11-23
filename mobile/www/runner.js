// Background checker (Capacitor Background Runner). Android runs it about every 15 minutes, even when the app is
// closed. It asks your inbox server whether a new feed run finished, and if so shows a notification.
// If the server sets KEEP_AWAKE_HOURS (e.g. "10-23"), it only checks inside that window so it never wakes a
// sleeping free-tier server at night. The app passes your phone's UTC offset, because this runtime has no time zone.
addEventListener("configure", (resolve, reject, args) => {
  try {
    CapacitorKV.set("token", args.token || "");
    CapacitorKV.set("base", args.base || "");
    CapacitorKV.set("awake", args.awake || "");
    CapacitorKV.set("tzOffset", args.tzOffset || "0");
    resolve();
  } catch (e) { reject(e); }
});

const kv = (k) => { const v = CapacitorKV.get(k); return (v && typeof v === "object" ? v.value : v) || ""; };

addEventListener("checkJobs", async (resolve, reject) => {
  try {
    const token = kv("token"), base = kv("base"), awake = kv("awake");
    if (!token || !base) { resolve(); return; }
    if (awake) {
      const [start, end] = awake.split("-").map(Number);
      const hour = Math.floor(((Date.now() / 3600000) + Number(kv("tzOffset") || 0) / 60) % 24 + 24) % 24;
      if (hour < start || hour >= end) { resolve(); return; }  // server sleeps at night
    }
    const r = await fetch(`${base}/api/ping?t=${token}`);
    if (!r.ok) { resolve(); return; }
    const s = await r.json();
    const seen = kv("lastRun");
    if (s.run_id && s.run_id !== seen) {
      CapacitorKV.set("lastRun", s.run_id);
      if (seen && s.new_leads > 0) {
        CapacitorNotifications.schedule([{
          id: Math.floor(Date.now() / 1000) % 2000000000,
          title: `${s.new_leads} new job${s.new_leads === 1 ? "" : "s"} for you`,
          body: `Today's matches are ready. ${s.waiting} waiting in New. Tap to open JobPilot.`,
          autoCancel: true,
        }]);
      }
    }
    resolve();
  } catch (e) { reject(e); }
});
