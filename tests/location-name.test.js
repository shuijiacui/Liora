const test = require('node:test');
const assert = require('node:assert/strict');
const {
  bigDataCloudUrl,
  cleanLocationName,
  locationNameFromBigDataCloud
} = require('../src/shared/location-name');

test('extracts and cleans a city name from the client-side fallback provider', () => {
  const url = new URL(bigDataCloudUrl({ latitude: 30.59, longitude: 114.31 }));
  assert.equal(url.hostname, 'api.bigdatacloud.net');
  assert.equal(url.searchParams.get('localityLanguage'), 'zh');
  assert.equal(locationNameFromBigDataCloud({ city: '武汉市', locality: '江汉区' }), '武汉');
  assert.equal(cleanLocationName('当前位置'), '');
});
