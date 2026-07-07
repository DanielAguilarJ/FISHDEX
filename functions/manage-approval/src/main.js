const sdk = require('node-appwrite');

module.exports = async ({ req, res, log, error }) => {
  const client = new sdk.Client();
  client
    .setEndpoint(process.env.APPWRITE_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    .setKey(process.env.APPWRITE_FUNCTION_API_KEY);

  const databases = new sdk.Databases(client);
  const teams = new sdk.Teams(client);
  const DATABASE_ID = 'fishdex_db';
  const USERS_COLLECTION = 'users';
  const APPROVAL_REQUESTS_COLLECTION = 'approval_requests';

  try {
    const { action, userId, requestId, adminId, rejectionReason } = JSON.parse(req.body);

    // Validate required fields
    if (!action || !userId || !requestId || !adminId) {
      return res.json({
        error: 'Missing required fields: action, userId, requestId, adminId',
      }, 400);
    }

    if (action !== 'approve' && action !== 'reject') {
      return res.json({
        error: 'Invalid action. Must be "approve" or "reject".',
      }, 400);
    }

    // Verify the caller has admin role
    const adminDoc = await databases.getDocument(DATABASE_ID, USERS_COLLECTION, adminId);

    if (!adminDoc || adminDoc.role !== 'admin') {
      error(`Unauthorized: user ${adminId} attempted admin action without admin role`);
      return res.json({ error: 'Unauthorized. Admin role required.' }, 403);
    }

    // Process the action
    if (action === 'approve') {
      // Update user's approval status
      await databases.updateDocument(DATABASE_ID, USERS_COLLECTION, userId, {
        approval_status: 'approved',
      });

      // Update the approval request document
      await databases.updateDocument(DATABASE_ID, APPROVAL_REQUESTS_COLLECTION, requestId, {
        status: 'approved',
        reviewed_by: adminId,
        reviewed_at: new Date().toISOString(),
      });

      log(`User ${userId} approved by admin ${adminId}`);
      return res.json({
        success: true,
        action: 'approve',
        userId,
        requestId,
        message: 'User has been approved successfully.',
      });
    } else if (action === 'reject') {
      // Update user's approval status
      await databases.updateDocument(DATABASE_ID, USERS_COLLECTION, userId, {
        approval_status: 'rejected',
      });

      // Update the approval request document
      const updateData = {
        status: 'rejected',
        reviewed_by: adminId,
        reviewed_at: new Date().toISOString(),
      };

      if (rejectionReason) {
        updateData.rejection_reason = rejectionReason;
      }

      await databases.updateDocument(DATABASE_ID, APPROVAL_REQUESTS_COLLECTION, requestId, updateData);

      log(`User ${userId} rejected by admin ${adminId}. Reason: ${rejectionReason || 'N/A'}`);
      return res.json({
        success: true,
        action: 'reject',
        userId,
        requestId,
        rejectionReason: rejectionReason || null,
        message: 'User has been rejected.',
      });
    }
  } catch (err) {
    error(`manage-approval error: ${err.message}`);
    return res.json({ error: 'Internal server error', details: err.message }, 500);
  }
};
