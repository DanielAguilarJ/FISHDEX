class LocalUser {
  final String id;
  final String email;
  final String name;
  final String role;

  LocalUser({
    required this.id,
    required this.email,
    required this.name,
    required this.role,
  });

  String get $id => id;

  factory LocalUser.fromJson(Map<String, dynamic> json) {
    return LocalUser(
      id: json['id'] as String,
      email: json['email'] as String,
      name: json['name'] as String,
      role: json['role'] as String? ?? 'fisherman',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'email': email,
      'name': name,
      'role': role,
    };
  }
}

class LocalSession {
  final String id;
  final String userId;

  LocalSession({
    required this.id,
    required this.userId,
  });

  String get $id => id;
}
