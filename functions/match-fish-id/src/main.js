const sdk = require('node-appwrite');

module.exports = async ({ req, res, log, error }) => {
  const client = new sdk.Client();
  client
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    .setKey(process.env.APPWRITE_FUNCTION_API_KEY);

  const databases = new sdk.Databases(client);
  const DATABASE_ID = 'fishdex_db';
  const COLLECTION_ID = 'fish_individuals';
  const MAX_DISTANCE_METERS = 5000;

  try {
    const { species, latitude, longitude } = JSON.parse(req.body);

    if (!species || latitude === undefined || longitude === undefined) {
      return res.json({ error: 'Missing required fields: species, latitude, longitude' }, 400);
    }

    // Query all individuals of the same species
    const response = await databases.listDocuments(DATABASE_ID, COLLECTION_ID, [
      sdk.Query.equal('species', species),
      sdk.Query.limit(1000),
    ]);

    // Haversine formula to calculate distance between two coordinates in meters
    function haversineDistance(lat1, lon1, lat2, lon2) {
      const R = 6371000; // Earth's radius in meters
      const toRad = (deg) => (deg * Math.PI) / 180;

      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

      return R * c;
    }

    let closestMatch = null;
    let closestDistance = Infinity;

    for (const doc of response.documents) {
      const dist = haversineDistance(
        latitude,
        longitude,
        doc.latitude,
        doc.longitude
      );

      if (dist < closestDistance) {
        closestDistance = dist;
        closestMatch = doc;
      }
    }

    if (closestMatch && closestDistance <= MAX_DISTANCE_METERS) {
      log(`Matched fish individual ${closestMatch.$id} at distance ${closestDistance.toFixed(2)}m`);
      return res.json({
        fish_id: closestMatch.$id,
        is_new: false,
        distance: Math.round(closestDistance),
      });
    }

    log(`No match found within ${MAX_DISTANCE_METERS}m for species "${species}". Closest was ${closestDistance.toFixed(2)}m`);
    return res.json({
      fish_id: null,
      is_new: true,
      distance: closestDistance === Infinity ? null : Math.round(closestDistance),
    });
  } catch (err) {
    error(`match-fish-id error: ${err.message}`);
    return res.json({ error: 'Internal server error', details: err.message }, 500);
  }
};
