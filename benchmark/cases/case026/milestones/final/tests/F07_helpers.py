# feature: F07
"""Application-owned schemas for public join scenarios; observations come from F05."""

JOIN_TABLES = r'''
    record JoinEntry(Object link, String label, boolean included) {}
    static Schema<JoinEntry> joinSchema(String labelColumn) {
        return Schema.<JoinEntry>builder().column("link", JoinEntry::link)
            .column(labelColumn, JoinEntry::label)
            .column("included", JoinEntry::included).build();
    }
'''
