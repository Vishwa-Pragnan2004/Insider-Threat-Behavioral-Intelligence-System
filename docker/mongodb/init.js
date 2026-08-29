// ============================================================
// ITBIS — MongoDB Initialization Script
// ============================================================
// Runs once when the MongoDB container is first created.
// ============================================================

// Switch to the application database
db = db.getSiblingDB('itbis_events');

// Create collections with basic validation schemas
db.createCollection('activity_events', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['event_type', 'timestamp', 'user_id'],
      properties: {
        event_type: { bsonType: 'string' },
        timestamp: { bsonType: 'date' },
        user_id: { bsonType: 'string' },
      }
    }
  }
});

db.createCollection('enriched_events');
db.createCollection('case_notes');
db.createCollection('alert_evidence');

// Create indexes for common query patterns
db.activity_events.createIndex({ user_id: 1, timestamp: -1 });
db.activity_events.createIndex({ event_type: 1, timestamp: -1 });
db.activity_events.createIndex({ timestamp: -1 });
db.enriched_events.createIndex({ user_id: 1, timestamp: -1 });

print('ITBIS MongoDB initialization complete.');
