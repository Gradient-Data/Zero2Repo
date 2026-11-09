# feature: F03
"""Application lifecycle support for observing compaction without close repair."""

COMPACTION_SUPPORT = r'''
    static void compactionExit() {
        // Match the reused caller's completion protocol, without a checkpoint,
        // close, or shutdown hook after the operation being observed.
        System.out.println("F02 checks completed");
        System.out.flush();
        Runtime.getRuntime().halt(0);
    }
'''
