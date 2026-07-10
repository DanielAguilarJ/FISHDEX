const sdk = require('node-appwrite');

// ── Constants ──────────────────────────────────────────────────────────────
const DATABASE_ID = 'fishdex_db';
const INDIVIDUALS_COLLECTION = 'fish_individuals';
const SIGHTINGS_COLLECTION = 'fish_sightings';
const MAX_DISTANCE_METERS = 2000;
const AWARD_XP_FUNCTION_ID = process.env.AWARD_XP_FUNCTION_ID || 'award-xp';

// ── Haversine ──────────────────────────────────────────────────────────────
function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371000; // Earth's radius in metres
  const toRad = (deg) => (deg * Math.PI) / 180;

  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
}

// ── Main handler ──────────────────────────────────────────────────────────
module.exports = async ({ req, res, log, error }) => {
  const client = new sdk.Client();
  client
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    .setKey(process.env.APPWRITE_FUNCTION_API_KEY);

  const databases = new sdk.Databases(client);
  const functions = new sdk.Functions(client);

  try {
    const body = JSON.parse(req.body);
    const { client_id, species, latitude, longitude, user_id } = body;

    if (!species || latitude === undefined || longitude === undefined || !user_id) {
      return res.json(
        { error: 'Missing required fields: species, latitude, longitude, user_id' },
        400,
      );
    }

    if (!client_id) {
      return res.json({ error: 'Missing required field: client_id' }, 400);
    }

    // ── 1. Find nearest same-species individual within radius ──────
    const response = await databases.listDocuments(DATABASE_ID, INDIVIDUALS_COLLECTION, [
      sdk.Query.equal('species', species),
      sdk.Query.limit(1000),
    ]);

    let closestMatch = null;
    let closestDistance = Infinity;

    for (const doc of response.documents) {
      const dist = haversineDistance(latitude, longitude, doc.latitude, doc.longitude);
      if (dist < closestDistance) {
        closestDistance = dist;
        closestMatch = doc;
      }
    }

    const isNewFish = !(closestMatch && closestDistance <= MAX_DISTANCE_METERS);
    const fishId = isNewFish ? null : closestMatch.$id;

    if (!isNewFish) {
      log(`Matched fish individual ${fishId} at ${closestDistance.toFixed(2)}m`);
    } else {
      log(
        `No match within ${MAX_DISTANCE_METERS}m for "${species}". ` +
          `Closest: ${closestDistance === Infinity ? 'none' : closestDistance.toFixed(2) + 'm'}`,
      );
    }

    // ── 2. Create sighting with client_id as document ID ───────────
    const sightingData = {
      userId: user_id,
      species,
      latitude,
      longitude,
      fish_id: fishId,
      is_new_fish: isNewFish,
      created_at: new Date().toISOString(),
      // Forward any extra fields the client sent
      ...(body.rarity && { rarity: body.rarity }),
      ...(body.photo_url && { photo_url: body.photo_url }),
      ...(body.notes && { notes: body.notes }),
    };

    let sightingDoc;
    let alreadyExisted = false;

    try {
      sightingDoc = await databases.createDocument(
        DATABASE_ID,
        SIGHTINGS_COLLECTION,
        client_id, // Use client-generated ID for idempotency
        sightingData,
      );
      log(`Created sighting ${sightingDoc.$id}`);
    } catch (createErr) {
      if (createErr.code === 409) {
        // Document already exists — idempotent success
        alreadyExisted = true;
        sightingDoc = await databases.getDocument(
          DATABASE_ID,
          SIGHTINGS_COLLECTION,
          client_id,
        );
        log(`Sighting ${client_id} already exists. Returning existing document.`);
      } else {
        throw createErr;
      }
    }

    // ── 3. Trigger award-xp (fire-and-forget, only on new create) ──
    if (!alreadyExisted) {
      try {
        await functions.createExecution(
          AWARD_XP_FUNCTION_ID,
          JSON.stringify({ user_id, sighting_id: sightingDoc.$id }),
          true, // async
        );
        log(`Triggered award-xp for sighting ${sightingDoc.$id}`);
      } catch (xpErr) {
        // Non-fatal: XP will be retried or reconciled later
        error(`Failed to trigger award-xp: ${xpErr.message}`);
      }
    }

    return res.json({
      sighting_id: sightingDoc.$id,
      fish_id: fishId,
      is_new_fish: isNewFish,
      already_existed: alreadyExisted,
      distance: closestDistance === Infinity ? null : Math.round(closestDistance),
    });
  } catch (err) {
    error(`match-fish-id error: ${err.message}`);
    return res.json({ error: 'Internal server error', details: err.message }, 500);
  }
};
