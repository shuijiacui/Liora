const { normalizeTranscript, removeWakeWord } = require('./voice-utils');

const SIGNALS = {
  reflection: [
    ['反思', 4], ['复盘', 4], ['整理思路', 4], ['聊聊', 3], ['聊一聊', 3],
    ['想法', 2], ['心情', 2], ['今天发生', 2], ['最近发生', 2],
    ['reflection', 4], ['reflect', 4], ['recap', 4], ['talk', 2], ['thought', 2]
  ],
  knowledge: [
    ['知识库', 4], ['知识', 4], ['笔记', 4], ['记了什么', 4], ['记录过', 3],
    ['保存过', 3], ['之前记', 3], ['以前记', 3], ['回顾记录', 3],
    ['knowledge', 4], ['notes', 4], ['note', 3], ['saved', 3], ['recorded', 3]
  ],
  weather: [
    ['天气', 4], ['气温', 4], ['温度', 4], ['下雨', 4], ['降雨', 4],
    ['带伞', 4], ['多少度', 4], ['冷不冷', 4], ['热不热', 4],
    ['weather', 4], ['temperature', 4], ['forecast', 4], ['rain', 4], ['umbrella', 4]
  ]
};

const PHRASE_BONUSES = {
  reflection: [
    /想.*(?:聊|说|谈)/u,
    /(?:陪我|帮我).*(?:反思|复盘|整理)/u,
    /(?:聊|说|谈).*(?:今天|最近|事情|想法)/u
  ],
  knowledge: [
    /(?:查看|看看|打开|回顾|找).*(?:知识|笔记|记录|内容)/u,
    /(?:记录|保存|记).*(?:什么|哪些)/u
  ],
  weather: [
    /天气.*(?:怎么样|如何|好吗|情况|预报|适合|出门)/u,
    /(?:今天|明天|现在).*(?:下雨|气温|温度|多少度)/u
  ]
};

function scoreIntent(normalized, intent) {
  let score = 0;
  for (const [signal, weight] of SIGNALS[intent]) {
    if (normalized.includes(normalizeTranscript(signal))) score += weight;
  }
  for (const pattern of PHRASE_BONUSES[intent]) {
    if (pattern.test(normalized)) score += 2;
  }
  return score;
}

function routeVoiceIntent(text) {
  const commandText = removeWakeWord(text);
  const normalized = normalizeTranscript(commandText);
  const scores = Object.fromEntries(
    ['reflection', 'knowledge', 'weather'].map((intent) => [intent, scoreIntent(normalized, intent)])
  );
  const ranked = Object.entries(scores).sort((left, right) => right[1] - left[1]);
  const [bestIntent, bestScore] = ranked[0];
  const secondScore = ranked[1][1];
  const margin = bestScore - secondScore;

  if (!normalized || bestScore < 3) {
    return { intent: null, confidence: 0, ambiguous: false, commandText, scores };
  }
  if (secondScore >= 4 && margin <= 3) {
    return { intent: null, confidence: 0.5, ambiguous: true, commandText, scores };
  }
  const confidence = Math.min(0.98, 0.58 + bestScore * 0.05 + margin * 0.025);
  return { intent: bestIntent, confidence, ambiguous: false, commandText, scores };
}

module.exports = { routeVoiceIntent, scoreIntent };
