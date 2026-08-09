(function exposeLocationNameHelpers(root, factory) {
  const helpers = factory();
  if (typeof module === 'object' && module.exports) module.exports = helpers;
  if (root) root.LioraLocationName = helpers;
})(typeof globalThis !== 'undefined' ? globalThis : this, () => {
  function cleanLocationName(value) {
    const name = String(value || '').trim().replace(/市$/, '');
    return ['这里', '当前位置'].includes(name) ? '' : name.slice(0, 60);
  }

  function bigDataCloudUrl(coordinates) {
    const url = new URL('https://api.bigdatacloud.net/data/reverse-geocode-client');
    url.searchParams.set('latitude', String(coordinates.latitude));
    url.searchParams.set('longitude', String(coordinates.longitude));
    url.searchParams.set('localityLanguage', 'zh');
    return url.toString();
  }

  function locationNameFromBigDataCloud(payload) {
    return cleanLocationName(
      payload?.city
      || payload?.locality
      || payload?.principalSubdivision
      || payload?.countryName
    );
  }

  return { bigDataCloudUrl, cleanLocationName, locationNameFromBigDataCloud };
});
