function asTimestamp(value) {
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function weatherReminderCandidates(snapshot, now = new Date()) {
  if (!snapshot?.current || !Array.isArray(snapshot.hourly)) return [];
  const nowTime = now.getTime();
  const candidates = [];
  const nextTwoHours = snapshot.hourly.filter((item) => {
    const time = asTimestamp(item.time);
    return time !== null && time >= nowTime && time <= nowTime + (2 * 60 * 60 * 1000);
  });
  const wettest = nextTwoHours.reduce((best, item) => {
    const probability = Number(item.precipitationProbability) || 0;
    const precipitation = Number(item.precipitation) || 0;
    if (probability < 60 || precipitation <= 0.1) return best;
    return !best || probability > best.precipitationProbability
      ? { ...item, precipitationProbability: probability }
      : best;
  }, null);

  if (wettest) {
    const hour = new Date(wettest.time).toISOString().slice(0, 13);
    candidates.push({
      key: `rain:${hour}`,
      priority: 20,
      title: 'Liora 提醒你带伞',
      body: `未来两小时降水概率最高 ${Math.round(wettest.precipitationProbability)}%。`
    });
  }

  const currentApparent = Number(snapshot.current.apparentTemperature);
  if (Number.isFinite(currentApparent)) {
    const nextTwelveHours = snapshot.hourly.filter((item) => {
      const time = asTimestamp(item.time);
      return time !== null && time >= nowTime && time <= nowTime + (12 * 60 * 60 * 1000);
    });
    let largestChange = null;
    for (const item of nextTwelveHours) {
      const apparent = Number(item.apparentTemperature);
      if (!Number.isFinite(apparent)) continue;
      const change = apparent - currentApparent;
      if (!largestChange || Math.abs(change) > Math.abs(largestChange.change)) {
        largestChange = { change, apparent };
      }
    }
    if (largestChange && Math.abs(largestChange.change) >= 7) {
      const direction = largestChange.change < 0 ? '降温' : '升温';
      const date = now.toISOString().slice(0, 10);
      candidates.push({
        key: `temperature:${direction}:${date}`,
        priority: 10,
        title: `今天会明显${direction}`,
        body: largestChange.change < 0 ? '晚些时候记得添件衣服。' : '体感温度会上升，注意及时调整衣物。'
      });
    }
  }

  return candidates.sort((left, right) => right.priority - left.priority);
}

module.exports = { weatherReminderCandidates };
