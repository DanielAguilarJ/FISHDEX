const sdk = require('node-appwrite');

// ── Constants ──────────────────────────────────────────────────────────────
const DATABASE_ID = 'fishdex_db';
const SIGHTINGS_COLLECTION = 'fish_sightings';
const XP_EVENTS_COLLECTION = 'xp_events';
const USERS_COLLECTION = 'users';
const ACHIEVEMENTS_COLLECTION = 'achievements';
const PAGE_SIZE = 100;

// XP table by rarity
const XP_BY_RARITY = {
  common: 10,
  uncommon: 25,
  rare: 50,
  legendary: 100,
};
const NEW_FISH_BONUS = 50;
const MAX_XP_PER_SIGHTING = 200;

// Achievement definitions
const ACHIEVEMENT_DEFS = [
  // Sighting milestones
  { id: 'sightings_1', type: 'sightings', threshold: 1, title: 'First Catch', description: 'Logged your first sighting' },
  { id: 'sightings_10', type: 'sightings', threshold: 10, title: 'Angler', description: 'Logged 10 sightings' },
  { id: 'sightings_50', type: 'sightings', threshold: 50, title: 'Seasoned Fisher', description: 'Logged 50 sightings' },
  { id: 'sightings_100', type: 'sightings', threshold: 100, title: 'Master Angler', description: 'Logged 100 sightings' },
  { id: 'sightings_500', type: 'sightings', threshold: 500, title: 'Living Legend', description: 'Logged 500 sightings' },
  // Species milestones
  { id: 'species_5', type: 'species', threshold: 5, title: 'Explorer', description: 'Discovered 5 species' },
  { id: 'species_10', type: 'species', threshold: 10, title: 'Naturalist', description: 'Discovered 10 species' },
  { id: 'species_25', type: 'species', threshold: 25, title: 'Taxonomist', description: 'Discovered 25 species' },
  // Level milestones
  { id: 'level_5', type: 'level', threshold: 5, title: 'Rising Tide', description: 'Reached level 5' },
  { id: 'level_10', type: 'level', threshold: 10, title: 'Deep Waters', description: 'Reached level 10' },
  { id: 'level_25', type: 'level', threshold: 25, title: 'Ocean Sage', description: 'Reached level 25' },
  // XP milestones
  { id: 'xp_1000', type: 'xp', threshold: 1000, title: 'XP Hunter', description: 'Earned 1,000 XP' },
  { id: 'xp_5000', type: 'xp', threshold: 5000, title: 'XP Veteran', description: 'Earned 5,000 XP' },
  { id: 'xp_10000', type: 'xp', threshold: 10000, title: 'XP Legend', description: 'Earned 10,000 XP' },
];

// ── Helpers ────────────────────────────────────────────────────────────────

/** Paginated fetch of all documents matching queries. */
async function fetchAll(databases, collectionId, extraQueries = []) {
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

/** Compute level from total XP using cumulative cost = 100 * level^1.5 per level. */
function computeLevel(totalXp) {
  let level = 0;
  let xpRemaining = totalXp;

  while (true) {
    const nextLevelCost = Math.floor(100 * Math.pow(level + 1, 1.5));
    if (xpRemaining < nextLevelCost) break;
    xpRemaining -= nextLevelCost;
    level++;
  }

  return level;
}

// ── Main handler ──────────────────────────────────────────────────────────
module.exports = async ({ req, res, log, error }) => {
  const client = new sdk.Client();
  client
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    .setKey(process.env.APPWRITE_FUNCTION_API_KEY);

  const databases = new sdk.Databases(client);

  try {
    const { user_id, sighting_id } = JSON.parse(req.body);

    if (!user_id || !sighting_id) {
      return res.json({ error: 'Missing required fields: user_id, sighting_id' }, 400);
    }

    // ── 1. Idempotency check: already awarded? ─────────────────────
    const existing = await databases.listDocuments(DATABASE_ID, XP_EVENTS_COLLECTION, [
      sdk.Query.equal('sighting_id', sighting_id),
      sdk.Query.equal('user_id', user_id),
      sdk.Query.limit(1),
    ]);

    if (existing.total > 0) {
      log(`XP already awarded for sighting ${sighting_id}. Skipping.`);
      return res.json({
        ok: true,
        already_awarded: true,
        xp_event_id: existing.documents[0].$id,
      });
    }

    // ── 2. Read sighting to determine rarity & new-fish flag ───────
    const sighting = await databases.getDocument(DATABASE_ID, SIGHTINGS_COLLECTION, sighting_id);
    const rarity = (sighting.rarity || 'common').toLowerCase();
    const isNewFish = sighting.is_new_fish === true;

    let xpAmount = XP_BY_RARITY[rarity] || XP_BY_RARITY.common;
    if (isNewFish) {
      xpAmount += NEW_FISH_BONUS;
    }
    xpAmount = Math.min(xpAmount, MAX_XP_PER_SIGHTING);

    log(`Sighting ${sighting_id}: rarity=${rarity}, is_new_fish=${isNewFish}, xp=${xpAmount}`);

    // ── 3. Create immutable XP event ───────────────────────────────
    const xpEvent = await databases.createDocument(
      DATABASE_ID,
      XP_EVENTS_COLLECTION,
      sdk.ID.unique(),
      {
        user_id,
        sighting_id,
        xp_amount: xpAmount,
        rarity,
        is_new_fish: isNewFish,
        awarded_at: new Date().toISOString(),
      },
    );
    log(`Created xp_event ${xpEvent.$id} (+${xpAmount} XP)`);

    // ── 4. Recompute total XP from ALL events (source of truth) ───
    const allEvents = await fetchAll(databases, XP_EVENTS_COLLECTION, [
      sdk.Query.equal('user_id', user_id),
    ]);

    const totalXp = allEvents.reduce((sum, evt) => sum + (evt.xp_amount || 0), 0);
    const level = computeLevel(totalXp);

    log(`User ${user_id}: total_xp=${totalXp}, level=${level}`);

    // ── 5. Update user document ────────────────────────────────────
    await databases.updateDocument(DATABASE_ID, USERS_COLLECTION, user_id, {
      total_xp: totalXp,
      level,
    });

    // ── 6. Evaluate achievements (idempotent) ──────────────────────
    // Gather counts for evaluation
    const allSightings = await databases.listDocuments(DATABASE_ID, SIGHTINGS_COLLECTION, [
      sdk.Query.equal('userId', user_id),
      sdk.Query.limit(1),
    ]);
    const sightingsCount = allSightings.total;

    // Count distinct species
    const allUserSightings = await fetchAll(databases, SIGHTINGS_COLLECTION, [
      sdk.Query.equal('userId', user_id),
    ]);
    const speciesSet = new Set(allUserSightings.map((s) => s.species).filter(Boolean));
    const speciesCount = speciesSet.size;

    // Build context for threshold checks
    const metricValues = {
      sightings: sightingsCount,
      species: speciesCount,
      level,
      xp: totalXp,
    };

    const newAchievements = [];

    for (const def of ACHIEVEMENT_DEFS) {
      const currentValue = metricValues[def.type] || 0;
      if (currentValue < def.threshold) continue;

      // Check if achievement already exists
      const achCheck = await databases.listDocuments(DATABASE_ID, ACHIEVEMENTS_COLLECTION, [
        sdk.Query.equal('user_id', user_id),
        sdk.Query.equal('achievement_id', def.id),
        sdk.Query.limit(1),
      ]);

      if (achCheck.total > 0) continue; // already earned

      // Award achievement
      const achDoc = await databases.createDocument(
        DATABASE_ID,
        ACHIEVEMENTS_COLLECTION,
        sdk.ID.unique(),
        {
          user_id,
          achievement_id: def.id,
          title: def.title,
          description: def.description,
          earned_at: new Date().toISOString(),
        },
      );
      newAchievements.push({ id: def.id, title: def.title, doc_id: achDoc.$id });
      log(`Achievement unlocked: ${def.title} (${def.id})`);
    }

    return res.json({
      ok: true,
      xp_event_id: xpEvent.$id,
      xp_awarded: xpAmount,
      total_xp: totalXp,
      level,
      new_achievements: newAchievements,
    });
  } catch (err) {
    error(`award-xp error: ${err.message}`);
    return res.json({ error: 'Internal server error', details: err.message }, 500);
  }
};
