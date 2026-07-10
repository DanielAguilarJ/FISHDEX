const sdk = require('node-appwrite');
const crypto = require('crypto');

// ── Constants ──────────────────────────────────────────────────────────────
const DATABASE_ID = 'fishdex_db';
const SIGHTINGS_COLLECTION = 'fish_sightings';
const USERS_COLLECTION = 'users';
const MASKING_RADIUS_METERS = 500;
const METERS_PER_DEG_LAT = 111320;
const PAGE_SIZE = 100;

// ── Coordinate masking ────────────────────────────────────────────────────
// Deterministic: same (fish_id + salt) always produces the same offset so
// repeated calls return consistent coordinates for the same individual.
function maskCoordinates(lat, lng, fishId, salt) {
  const hash = crypto
    .createHash('sha256')
    .update(fishId + salt)
    .digest();

  // Two uniform floats [0,1) from first 8 bytes of the hash
  const r1 = hash.readUInt32BE(0) / 0xffffffff; // angle seed
  const r2 = hash.readUInt32BE(4) / 0xffffffff; // distance seed

  // Uniform distribution inside a circle (sqrt for area-uniform radius)
  const angle = r1 * 2 * Math.PI;
  const distance = Math.sqrt(r2) * MASKING_RADIUS_METERS;

  // Convert metres to degrees, accounting for latitude
  const latRad = lat * (Math.PI / 180);
  const metersPerDegLng = METERS_PER_DEG_LAT * Math.cos(latRad);

  const dLat = (distance * Math.sin(angle)) / METERS_PER_DEG_LAT;
  const dLng = (distance * Math.cos(angle)) / metersPerDegLng;

  return {
    latitude: lat + dLat,
    longitude: lng + dLng,
  };
}

// ── Paginated fetch ───────────────────────────────────────────────────────
async function fetchAllDocuments(databases, collectionId, extraQueries = []) {
  const all = [];
  let offset = 0;
  let hasMore = true;

  while (hasMore) {
    const queries = [
      sdk.Query.limit(PAGE_SIZE),
      sdk.Query.offset(offset),
      ...extraQueries,
    ];
    const batch = await databases.listDocuments(DATABASE_ID, collectionId, queries);
    all.push(...batch.documents);
    offset += PAGE_SIZE;
    hasMore = batch.documents.length === PAGE_SIZE;
  }

  return all;
}

// ── Main handler ──────────────────────────────────────────────────────────
module.exports = async ({ req, res, log, error }) => {
  const client = new sdk.Client();
  client
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    .setKey(process.env.APPWRITE_FUNCTION_API_KEY);

  const databases = new sdk.Databases(client);
  const COORDINATE_SALT = process.env.COORDINATE_SALT || '';

  try {
    const { userId } = JSON.parse(req.body);

    if (!userId) {
      return res.json({ error: 'Missing required field: userId' }, 400);
    }

    // ── Step 1: Server-side role verification ─────────────────────────
    let userDoc;
    try {
      userDoc = await databases.getDocument(DATABASE_ID, USERS_COLLECTION, userId);
    } catch (lookupErr) {
      error(`User lookup failed for ${userId}: ${lookupErr.message}`);
      return res.json({ error: 'User not found' }, 404);
    }

    const verifiedRole = (userDoc.role || 'fisherman').toLowerCase();
    log(`Verified role for ${userId}: ${verifiedRole}`);

    // ── Step 2: Fetch sightings based on verified role ────────────────
    let documents;

    if (verifiedRole === 'researcher' || verifiedRole === 'admin') {
      // Privileged roles see everything, unmasked
      documents = await fetchAllDocuments(databases, SIGHTINGS_COLLECTION);
      log(`Returning ${documents.length} total captures for ${verifiedRole} ${userId}`);

      return res.json({
        total: documents.length,
        captures: documents,
      });
    }

    // ── Fisherman: own sightings only ─────────────────────────────────
    documents = await fetchAllDocuments(databases, SIGHTINGS_COLLECTION, [
      sdk.Query.equal('userId', userId),
    ]);
    log(`Returning ${documents.length} captures for fisherman ${userId}`);

    // Apply coordinate masking to any document NOT owned by this user
    // (safety net — the query already filters, but if ownership data
    //  changes or additional visibility rules are added later this
    //  still protects coordinates.)
    const masked = documents.map((doc) => {
      if (doc.userId !== userId && doc.latitude != null && doc.longitude != null) {
        const offset = maskCoordinates(
          doc.latitude,
          doc.longitude,
          doc.fish_id || doc.$id,
          COORDINATE_SALT,
        );
        return {
          ...doc,
          latitude: offset.latitude,
          longitude: offset.longitude,
          _coordinates_masked: true,
        };
      }
      return doc;
    });

    return res.json({
      total: masked.length,
      captures: masked,
    });
  } catch (err) {
    error(`get-captures-by-role error: ${err.message}`);
    return res.json({ error: 'Internal server error', details: err.message }, 500);
  }
};
