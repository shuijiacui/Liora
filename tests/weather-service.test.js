const test = require('node:test');
const assert = require('node:assert/strict');
const {
  WeatherService,
  configuredWeatherSettings,
  locationNameFromGeocode,
  normalizeForecast,
  reverseGeocodeUrl,
  roundedCoordinates,
  weatherLocationKey,
  weatherLocationNeedsName
} = require('../src/services/weather-service');
const { weatherReminderCandidates } = require('../src/shared/weather-rules');

function forecastAt(times) {
  return {
    current: { temperature_2m: 20, apparent_temperature: 20, weather_code: 2 },
    hourly: {
      time: times,
      apparent_temperature: [20, 19, 12],
      precipitation_probability: [10, 80, 20],
      precipitation: [0, 1.2, 0],
      weather_code: [2, 61, 3]
    }
  };
}

test('weather is opt-in through valid coordinates', () => {
  assert.equal(configuredWeatherSettings({}).enabled, false);
  assert.equal(configuredWeatherSettings({
    LIORA_WEATHER_LATITUDE: '120',
    LIORA_WEATHER_LONGITUDE: '121.47'
  }).enabled, false);
  const settings = configuredWeatherSettings({
    LIORA_WEATHER_LATITUDE: '31.23',
    LIORA_WEATHER_LONGITUDE: '121.47',
    LIORA_WEATHER_LOCATION: '上海'
  });
  assert.equal(settings.enabled, true);
  assert.equal(settings.location, '上海');
});

test('saved automatic location takes precedence and is reduced to city-level precision', () => {
  const settings = configuredWeatherSettings(
    {
      LIORA_WEATHER_LATITUDE: '31.23',
      LIORA_WEATHER_LONGITUDE: '121.47',
      LIORA_WEATHER_LOCATION: '上海'
    },
    {
      enabled: true,
      latitude: 39.904211,
      longitude: 116.407395,
      location: '当前位置',
      source: 'geolocation'
    }
  );
  assert.deepEqual(
    { latitude: settings.latitude, longitude: settings.longitude, source: settings.source },
    { latitude: 39.9, longitude: 116.41, source: 'geolocation' }
  );
  assert.deepEqual(roundedCoordinates(91, 0), null);
});

test('only unresolved current coordinates need a background city lookup', () => {
  const unresolved = {
    enabled: true,
    latitude: 30.43,
    longitude: 111.75,
    location: '当前位置'
  };
  assert.equal(weatherLocationKey(unresolved), '30.43,111.75');
  assert.equal(weatherLocationNeedsName(unresolved), true);
  assert.equal(weatherLocationNeedsName({ ...unresolved, location: '宜昌' }), false);
  assert.equal(weatherLocationNeedsName({ ...unresolved, enabled: false }), false);
});

test('normalizes provider arrays into a shared weather snapshot', () => {
  const payload = forecastAt(['2026-08-08T10:00', '2026-08-08T11:00', '2026-08-08T18:00']);
  const snapshot = normalizeForecast(
    payload,
    { location: '上海' },
    new Date('2026-08-08T10:00:00+08:00')
  );
  assert.equal(snapshot.location, '上海');
  assert.equal(snapshot.hourly[1].precipitationProbability, 80);
});

test('builds a city-level reverse geocode request and extracts a Chinese city name', () => {
  const url = new URL(reverseGeocodeUrl({ latitude: 30.59, longitude: 114.31 }));
  assert.equal(url.hostname, 'nominatim.openstreetmap.org');
  assert.equal(url.searchParams.get('zoom'), '10');
  assert.equal(locationNameFromGeocode({ address: { city: '武汉市', state: '湖北省' } }), '武汉');
});

test('produces actionable rain and temperature reminders', () => {
  const now = new Date('2026-08-08T10:00:00+08:00');
  const snapshot = normalizeForecast(
    forecastAt(['2026-08-08T10:00:00+08:00', '2026-08-08T11:00:00+08:00', '2026-08-08T18:00:00+08:00']),
    { location: '上海' },
    now
  );
  const reminders = weatherReminderCandidates(snapshot, now);
  assert.equal(reminders[0].key.startsWith('rain:'), true);
  assert.equal(reminders.some((item) => item.key.includes('降温')), true);
});

test('does not emit the same weather reminder twice during one run', async () => {
  const now = new Date('2026-08-08T10:00:00+08:00');
  const payload = forecastAt([
    '2026-08-08T10:00:00+08:00',
    '2026-08-08T11:00:00+08:00',
    '2026-08-08T18:00:00+08:00'
  ]);
  const service = new WeatherService(
    { enabled: true, latitude: 31.23, longitude: 121.47, location: '上海' },
    { fetchJson: async () => payload, now: () => now }
  );
  let count = 0;
  service.on('reminder', () => { count += 1; });
  await service.refresh();
  await service.refresh();
  assert.equal(count, 1);
});
