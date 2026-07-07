const sdk = require('node-appwrite');

module.exports = async ({ req, res, log, error }) => {
  const client = new sdk.Client();
  client
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    .setKey(process.env.APPWRITE_FUNCTION_API_KEY);

  const databases = new sdk.Databases(client);
  const DATABASE_ID = 'fishdex_db';
  const COLLECTION_ID = 'fish_sightings';

  try {
    const { userId, role } = JSON.parse(req.body);

    if (!userId || !role) {
      return res.json({ error: 'Missing required fields: userId, role' }, 400);
    }

    let queries = [sdk.Query.limit(1000)];
    let documents;

    if (role === 'fisherman') {
      // Fishermen can only see their own captures
      queries.push(sdk.Query.equal('userId', userId));
      const response = await databases.listDocuments(DATABASE_ID, COLLECTION_ID, queries);
      documents = response.documents;
      log(`Returning ${documents.length} captures for fisherman ${userId}`);
    } else if (role === 'researcher' || role === 'admin') {
      // Researchers and admins can see all captures with full data
      const response = await databases.listDocuments(DATABASE_ID, COLLECTION_ID, queries);
      documents = response.documents;
      log(`Returning ${documents.length} total captures for ${role} ${userId}`);
    } else {
      return res.json({ error: `Invalid role: ${role}. Must be fisherman, researcher, or admin.` }, 403);
    }

    return res.json({
      total: documents.length,
      captures: documents,
    });
  } catch (err) {
    error(`get-captures-by-role error: ${err.message}`);
    return res.json({ error: 'Internal server error', details: err.message }, 500);
  }
};
