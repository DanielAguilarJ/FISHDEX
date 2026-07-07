import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/repositories/roles_repository.dart';

/// Panel de administración para gestionar solicitudes de investigadores
/// y ver estadísticas generales del sistema.
/// Solo accesible para usuarios con rol admin.
class AdminPanelScreen extends ConsumerStatefulWidget {
  const AdminPanelScreen({super.key});

  @override
  ConsumerState<AdminPanelScreen> createState() => _AdminPanelScreenState();
}

class _AdminPanelScreenState extends ConsumerState<AdminPanelScreen> {
  List<Map<String, dynamic>> _pendingApprovals = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadPendingApprovals();
  }

  Future<void> _loadPendingApprovals() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final databases = ref.read(appwriteDatabasesProvider);
      final rolesRepo = RolesRepository(databases: databases);
      final approvals = await rolesRepo.getPendingApprovals();

      setState(() {
        _pendingApprovals = approvals;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Error al cargar solicitudes: $e';
        _isLoading = false;
      });
    }
  }

  Future<void> _handleApproval(
    Map<String, dynamic> request,
    bool approve,
  ) async {
    try {
      final databases = ref.read(appwriteDatabasesProvider);
      final rolesRepo = RolesRepository(databases: databases);
      final account = ref.read(appwriteAccountProvider);
      final admin = await account.get();

      final userId = request['user_id'] as String;
      final requestId = request['\$id'] as String;

      bool success;
      if (approve) {
        success = await rolesRepo.approveResearcher(
          userId: userId,
          requestId: requestId,
          adminId: admin.$id,
        );
      } else {
        success = await rolesRepo.rejectResearcher(
          userId: userId,
          requestId: requestId,
          adminId: admin.$id,
        );
      }

      if (success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(approve
                ? 'Investigador aprobado correctamente'
                : 'Solicitud rechazada'),
            backgroundColor: approve ? Colors.green : Colors.orange,
          ),
        );
        _loadPendingApprovals(); // Refresh
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text(
          'PANEL DE ADMIN',
          style: TextStyle(
            color: Colors.white,
            letterSpacing: 2,
            fontWeight: FontWeight.bold,
          ),
        ),
        actions: [
          IconButton(
            onPressed: _loadPendingApprovals,
            icon: const Icon(Icons.refresh, color: Colors.white70),
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _buildErrorState()
              : _buildContent(),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Colors.red, size: 48),
          const SizedBox(height: 16),
          Text(
            _error!,
            style: const TextStyle(color: Colors.red),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _loadPendingApprovals,
            child: const Text('Reintentar'),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sección: Solicitudes Pendientes
          _buildSectionHeader(
            'Solicitudes Pendientes',
            Icons.pending_actions,
            badge: _pendingApprovals.length,
          ),
          const SizedBox(height: 12),

          if (_pendingApprovals.isEmpty)
            _buildEmptyState()
          else
            ..._pendingApprovals.map((request) => _buildApprovalCard(request)),

          const SizedBox(height: 32),

          // Sección: Stats rápidas
          _buildSectionHeader('Estadísticas', Icons.analytics),
          const SizedBox(height: 12),
          _buildStatsGrid(),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title, IconData icon, {int? badge}) {
    return Row(
      children: [
        Icon(icon, color: AppTheme.accentBlue, size: 22),
        const SizedBox(width: 10),
        Text(
          title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
        if (badge != null && badge > 0) ...[
          const SizedBox(width: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: Colors.red,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              badge.toString(),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildEmptyState() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.03),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.05)),
      ),
      child: Column(
        children: [
          Icon(
            Icons.check_circle_outline,
            color: Colors.green.withOpacity(0.5),
            size: 48,
          ),
          const SizedBox(height: 12),
          Text(
            'No hay solicitudes pendientes',
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildApprovalCard(Map<String, dynamic> request) {
    final username = request['username'] as String? ?? 'Usuario';
    final institution = request['institution'] as String? ?? '';
    final reason = request['reason'] as String? ?? '';
    final requestedAt = request['requested_at'] as String? ?? '';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.orange.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: nombre + badge
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: AppTheme.legendaryGradient,
                ),
                child: const Icon(Icons.biotech, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      username,
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                      ),
                    ),
                    if (institution.isNotEmpty)
                      Text(
                        institution,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                          fontSize: 12,
                        ),
                      ),
                  ],
                ),
              ),
              // Fecha
              Text(
                _formatDate(requestedAt),
                style: TextStyle(
                  color: Colors.white.withOpacity(0.4),
                  fontSize: 11,
                ),
              ),
            ],
          ),

          // Motivo
          if (reason.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.03),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                reason,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.7),
                  fontSize: 13,
                  height: 1.3,
                ),
              ),
            ),
          ],

          const SizedBox(height: 16),

          // Botones de acción
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _handleApproval(request, false),
                  icon: const Icon(Icons.close, size: 18),
                  label: const Text('Rechazar'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.red,
                    side: const BorderSide(color: Colors.red),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () => _handleApproval(request, true),
                  icon: const Icon(Icons.check, size: 18),
                  label: const Text('Aprobar'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStatsGrid() {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      childAspectRatio: 1.6,
      children: [
        _buildStatCard('Pendientes', _pendingApprovals.length.toString(),
            Icons.pending, Colors.orange),
        _buildStatCard(
            'Capturas Hoy', '-', Icons.phishing, AppTheme.accentBlue),
        _buildStatCard(
            'Usuarios', '-', Icons.people, AppTheme.teal),
        _buildStatCard(
            'Especies', '-', Icons.pets, Colors.green),
      ],
    );
  }

  Widget _buildStatCard(
      String label, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: color, size: 24),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  String _formatDate(String isoDate) {
    try {
      final date = DateTime.parse(isoDate);
      return '${date.day}/${date.month}/${date.year}';
    } catch (_) {
      return '';
    }
  }
}
