const { EventEmitter } = require('node:events');
const { cleanLocationName } = require('../shared/location-name');
const { weatherReminderCandidates } = require('../shared/weather-rules');

const REFRESH_INTERVAL_MS = 30 * 60 * 1000;

function validCoordinates(latitude, longitude) {
  return Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180;
}

function roundedCoordinates(latitude, longitude) {
  const normalizedLatitude = Number(latitude);
  const normalizedLongitude = Number(longitude);
  if (!validCoordinates(normalizedLatitude, normalizedLongitude)) return null;
  return {
    latitude: Math.round(normalizedLatitude * 100) / 100,
    longitude: Math.round(normalizedLongitude * 100) / 100
  };
}

function weatherLocationKey(settings = {}) {
  const coordinates = roundedCoordinates(settings.latitude, settings.longitude);
  return coordinates ? `${coordinates.latitude},${coordinates.longitude}` : '';
}

function weatherLocationNeedsName(settings = {}) {
  return Boolean(
    settings.enabled
    && weatherLocationKey(settings)
    && !cleanLocationName(settings.location)
  );
}

function configuredWeatherSettings(env = process.env, saved = {}) {
  const latitudeText = String(env.LIORA_WEATHER_LATITUDE || '').trim();
  const longitudeText = String(env.LIORA_WEATHER_LONGITUDE || '').trim();
  const environmentCoordinates = latitudeText && longitudeText
    ? roundedCoordinates(latitudeText, longitudeText)
    : null;
  const savedCoordinates = roundedCoordinates(saved.latitude, saved.longitude);
  const coordinates = savedCoordinates || environmentCoordinates;
  const savedSelected = Boolean(savedCoordinates);
  return {
    enabled: Boolean(coordinates)
      && (savedSelected ? saved.enabled !== false : env.LIORA_WEATHER_ENABLED !== '0'),
    latitude: coordinates?.latitude ?? null,
    longitude: coordinates?.longitude ?? null,
    location: savedSelected
      ? String(saved.location || '').trim() || '当前位置'
      : String(env.LIORA_WEATHER_LOCATION || '').trim() || '当前位置',
    source: savedSelected ? String(saved.source || 'saved') : environmentCoordinates ? 'environment' : 'none'
  };
}

function forecastUrl(settings) {
  const url = new URL('https://api.open-meteo.com/v1/forecast');
  url.searchParams.set('latitude', String(settings.latitude));
  url.searchParams.set('longitude', String(settings.longitude));
  url.searchParams.set('current', 'temperature_2m,apparent_temperature,weather_code');
  url.searchParams.set(
    'hourly',
    'apparent_temperature,precipitation_probability,precipitation,weather_code'
  );
  url.searchParams.set('forecast_days', '2');
  url.searchParams.set('timezone', 'auto');
  url.searchParams.set('timeformat', 'unixtime');
  return url.toString();
}

function normalizeForecastTime(value) {
  return typeof value === 'number' ? new Date(value * 1000).toISOString() : value;
}

function normalizeForecast(payload, settings, updatedAt = new Date()) {
  const hourly = payload?.hourly || {};
  const times = Array.isArray(hourly.time) ? hourly.time : [];
  return {
    configured: true,
    location: settings.location,
    updatedAt: updatedAt.toISOString(),
    current: {
      temperature: Number(payload?.current?.temperature_2m),
      apparentTemperature: Number(payload?.current?.apparent_temperature),
      weatherCode: Number(payload?.current?.weather_code)
    },
    hourly: times.map((time, index) => ({
      time: normalizeForecastTime(time),
      apparentTemperature: Number(hourly.apparent_temperature?.[index]),
      precipitationProbability: Number(hourly.precipitation_probability?.[index]),
      precipitation: Number(hourly.precipitation?.[index]),
      weatherCode: Number(hourly.weather_code?.[index])
    }))
  };
}

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    if (!response.ok) throw new Error(`weather request failed (${response.status})`);
    return response.json();
  } finally {
    clearTimeout(timer);
  }
}

function reverseGeocodeUrl(coordinates) {
  const url = new URL('https://nominatim.openstreetmap.org/reverse');
  url.searchParams.set('lat', String(coordinates.latitude));
  url.searchParams.set('lon', String(coordinates.longitude));
  url.searchParams.set('format', 'jsonv2');
  url.searchParams.set('zoom', '10');
  url.searchParams.set('addressdetails', '1');
  url.searchParams.set('layer', 'address');
  url.searchParams.set('accept-language', 'zh-CN,zh,en');
  return url.toString();
}

function locationNameFromGeocode(payload) {
  const address = payload?.address || {};
  const value = [
    address.city,
    address.municipality,
    address.town,
    address.county,
    address.state_district,
    address.state,
    payload?.name
  ].find((item) => String(item || '').trim());
  return String(value || '').trim().replace(/市$/, '') || '当前位置';
}

async function reverseGeocodeLocation(coordinates, requestJson = fetchJson) {
  const payload = await requestJson(reverseGeocodeUrl(coordinates), {
    headers: {
      'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
      'User-Agent': 'Liora-Desktop-Companion/0.2'
    }
  });
  return locationNameFromGeocode(payload);
}

class WeatherService extends EventEmitter {
  constructor(settings, options = {}) {
    super();
    this.settings = settings;
    this.fetchJson = options.fetchJson || fetchJson;
    this.now = options.now || (() => new Date());
    this.intervalMs = options.intervalMs || REFRESH_INTERVAL_MS;
    this.reminderCooldownMs = options.reminderCooldownMs || (3 * 60 * 60 * 1000);
    this.timer = null;
    this.snapshot = { configured: Boolean(settings.enabled), location: settings.location };
    this.notified = new Set();
    this.lastReminderAt = null;
  }

  status() {
    return this.snapshot;
  }

  start() {
    if (!this.settings.enabled || this.timer) return;
    void this.refresh().catch((error) => this.emit('warning', error));
    this.timer = setInterval(() => {
      void this.refresh().catch((error) => this.emit('warning', error));
    }, this.intervalMs);
    this.timer.unref?.();
  }

  stop() {
    clearInterval(this.timer);
    this.timer = null;
  }

  async refresh() {
    const now = this.now();
    const payload = await this.fetchJson(forecastUrl(this.settings));
    this.snapshot = normalizeForecast(payload, this.settings, now);
    this.emit('update', this.snapshot);

    const reminder = weatherReminderCandidates(this.snapshot, now).find(
      (candidate) => !this.notified.has(candidate.key)
    );
    const outsideCooldown = !this.lastReminderAt
      || now.getTime() - this.lastReminderAt.getTime() >= this.reminderCooldownMs;
    if (reminder && outsideCooldown) {
      this.notified.add(reminder.key);
      this.lastReminderAt = now;
      this.emit('reminder', reminder);
    }
    return this.snapshot;
  }
}

module.exports = {
  WeatherService,
  configuredWeatherSettings,
  forecastUrl,
  normalizeForecast,
  locationNameFromGeocode,
  reverseGeocodeLocation,
  reverseGeocodeUrl,
  roundedCoordinates,
  weatherLocationKey,
  weatherLocationNeedsName
};
