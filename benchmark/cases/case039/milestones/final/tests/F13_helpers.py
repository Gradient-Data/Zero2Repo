# feature: F13
"""View observations through public SQL and fully consumed native results."""
from F06_helpers import RUST_TRANSACTION_SUPPORT

VIEW_SUPPORT = RUST_TRANSACTION_SUPPORT + r'''
fn view_base(db: &Database) {
    exec(db,"CREATE TABLE stock (id INTEGER PRIMARY KEY, label TEXT, amount INTEGER, enabled BOOLEAN)");
    exec(db,"INSERT INTO stock VALUES (3,'birch',8,TRUE),(1,'cedar',5,TRUE),(4,'elm',9,FALSE),(2,'ash',2,TRUE)");
}
fn view_definitions(db: &Database) {
    exec(db,"CREATE VIEW offers AS SELECT id AS item, label AS title, amount*3+1 AS total FROM stock WHERE enabled=TRUE AND amount>=3");
    exec(db,"CREATE VIEW selected AS SELECT item,title,total-2 AS adjusted FROM offers WHERE total>=20");
}
fn view_named(rows: Vec<ResultRow>, number: &str) -> Vec<(i64,String,i64)> {
    let got=rows.iter().map(|r|(r.get_by_name("item").unwrap(),
        r.get_by_name("title").unwrap(),r.get_by_name(number).unwrap())).collect();
    println!("view rows ({number}): {got:?}"); got
}
fn view_rows(db: &Database, sql: &str, number: &str) -> Vec<(i64,String,i64)> {
    view_named(read_rows(db,sql).unwrap(),number)
}
fn view_tx_rows(tx: &mut Transaction, sql: &str, number: &str) -> Vec<(i64,String,i64)> {
    view_named(tx.query(sql,()).and_then(|r|r.collect_vec()).unwrap(),number)
}
fn view_catalog(db: &Database) -> Vec<String> {
    let mut names:Vec<String>=read_rows(db,"SHOW VIEWS").unwrap().iter()
        .map(|r|r.get_by_name("view_name").unwrap()).collect();
    names.sort(); println!("view catalog: {names:?}"); names
}
fn view_definition(db: &Database, name: &str) -> String {
    let rows=read_rows(db,&format!("SHOW CREATE VIEW {name}")).unwrap();
    assert_eq!(rows.len(),1);
    assert_eq!(rows[0].get_by_name::<String>("View").unwrap(),name);
    let definition=rows[0].get_by_name::<String>("Create View").unwrap();
    println!("saved definition: {definition}"); definition
}
fn view_stock(db: &Database) -> Vec<(i64,String,i64,bool)> {
    let rows=read_rows(db,"SELECT id,label,amount,enabled FROM stock ORDER BY id").unwrap();
    let got=rows.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap(),r.get(2).unwrap(),r.get(3).unwrap())).collect();
    println!("base rows: {got:?}"); got
}
'''
