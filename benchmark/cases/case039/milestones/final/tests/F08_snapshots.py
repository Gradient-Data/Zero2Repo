# feature: F08
"""Read the documented backup identity carrier; backup contents remain opaque."""
import re
from pathlib import Path


def snapshot_ids(directory, table):
    folder = Path(directory) / "snapshots" / table
    identities = set()
    for path in folder.iterdir():
        match = re.fullmatch(r"snapshot-([0-9]{8}-[0-9]{6}\.[0-9]{3})\.bin", path.name)
        if match:
            assert path.is_file(), path
            identities.add(match[1])
    return identities


RUST_SNAPSHOT_SUPPORT = r'''
fn snapshot_ids(path: &str,table: &str)->std::collections::BTreeSet<String> {
    let folder=std::path::Path::new(path).join("snapshots").join(table);
    let mut identities=std::collections::BTreeSet::new();
    for entry in std::fs::read_dir(folder).unwrap() {
        let entry=entry.unwrap();let name=entry.file_name();let name=name.to_str().unwrap();
        if let Some(id)=name.strip_prefix("snapshot-").and_then(|s|s.strip_suffix(".bin")) {
            let is_identity=id.len()==19 && id.bytes().enumerate().all(|(i,b)|
                if i==8 {b==b'-'} else if i==15 {b==b'.'} else {b.is_ascii_digit()});
            if is_identity {
                assert!(entry.file_type().unwrap().is_file());
                assert!(identities.insert(id.to_string()));
            }
        }
    }
    identities
}
'''
