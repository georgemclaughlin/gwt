"use strict";
// Pure checkpoint and clock operations, shared by the inline page and Node tests.
// This validates cooperative observations; it does not authenticate their author.
globalThis.GwtReviewRecovery = (() => {
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const sameKeys = (a, b) => object(a) && object(b) &&
    Object.keys(a).length === Object.keys(b).length && Object.keys(b).every(k => Object.hasOwn(a, k));
  const requireValue = (condition, message) => { if (!condition) throw new Error(message); };
  const finiteDuration = value => typeof value === "number" && Number.isFinite(value) && value >= 0;

  function restore(packet, saved) {
    requireValue(packet.responseSchemaVersion === 2 && object(saved) && saved.schemaVersion === 2,
      "This file does not support checkpoint recovery.");
    for (const name of ["packetId", "assignmentId", "purpose"]) {
      requireValue(saved[name] === packet[name], "The checkpoint belongs to a different session.");
    }
    requireValue(typeof saved.responseId === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(saved.responseId),
      "Invalid response identity.");
    const profile = saved.profile;
    requireValue(object(profile) && ["developer", "domain_specialist", "other"].includes(profile.role) &&
      ["yes", "no", "unsure"].includes(profile.priorExposure) &&
      ["gwtFamiliarity", "pythonFamiliarity"].every(k => Number.isInteger(profile[k]) && profile[k] >= 0 && profile[k] <= 3),
      "The checkpoint has an invalid profile.");
    requireValue(saved.finished === false, "A completed review cannot be resumed.");
    requireValue(Array.isArray(saved.tasks) && saved.tasks.length === packet.tasks.length,
      "The checkpoint must contain every assigned task.");
    let draft = -1;
    for (let i = 0; i < packet.tasks.length; i++) {
      const task = packet.tasks[i], row = saved.tasks[i];
      requireValue(object(row) && row.id === task.id && sameKeys(row.sourceDigests, task.sourceDigests) &&
        Object.keys(task.sourceDigests).every(k => row.sourceDigests[k] === task.sourceDigests[k]),
        "Task order or source identity differs from this session.");
      requireValue(["submitted", "skipped", "draft", "unseen"].includes(row.status), "Invalid task status.");
      requireValue(draft < 0 ? row.status !== "unseen" : row.status === "unseen", "Task order is invalid.");
      if (row.status === "draft") draft = i;
      requireValue(Number.isInteger(row.resumeCount) && row.resumeCount >= 0 && row.resumeCount <= 1000000,
        "Invalid recovery count.");
      if (row.status === "unseen") {
        requireValue(row.activeMs === null && row.wallMs === null && row.resumeCount === 0,
          "Unseen tasks cannot contain timing or recoveries.");
      } else {
        requireValue(finiteDuration(row.activeMs) && finiteDuration(row.wallMs) && row.activeMs <= row.wallMs,
          "Invalid task timing.");
      }
      const questions = Object.fromEntries(task.questions.map(q => [q.id, q]));
      requireValue(sameKeys(row.predictions, questions), "Prediction questions differ from this session.");
      for (const q of task.questions) {
        requireValue(row.predictions[q.id] === null || q.choices.some(c => c.id === row.predictions[q.id]),
          "Unknown prediction choice.");
      }
      requireValue([null, "approve", "request_changes", "unsure"].includes(row.recommendation),
        "Invalid recommendation.");
      requireValue(row.confidence === null || (Number.isInteger(row.confidence) && row.confidence >= 1 && row.confidence <= 5),
        "Invalid confidence.");
      requireValue(typeof row.rationale === "string" && row.rationale.length <= 10000, "Invalid explanation.");
      const anyPrediction = Object.values(row.predictions).some(v => v !== null);
      if (row.status === "unseen") {
        requireValue(!anyPrediction && row.recommendation === null && row.confidence === null && row.rationale === "",
          "Unseen tasks cannot contain answers.");
      }
      if (row.status === "submitted") {
        requireValue(Object.values(row.predictions).every(v => v !== null) && row.recommendation !== null &&
          row.confidence !== null && row.rationale.trim() !== "", "Submitted tasks need complete answers.");
      }
    }
    requireValue(draft >= 0, "The checkpoint has no interrupted task.");
    requireValue(saved.tasks[draft].resumeCount < 1000000, "Recovery count limit reached.");
    const response = JSON.parse(JSON.stringify(saved));
    delete response.exportedAt;
    response.tasks[draft].resumeCount++;
    return {response, index: draft};
  }

  function startClock(row, now, counting) {
    return {active: row.activeMs ?? 0, wallBase: row.wallMs ?? 0, started: now, last: now, counting};
  }

  function tick(clock, now, counting) {
    if (clock.counting) clock.active += now - clock.last;
    clock.last = now;
    clock.counting = counting;
    return {activeMs: clock.active, wallMs: clock.wallBase + now - clock.started};
  }

  return {restore, startClock, tick};
})();
