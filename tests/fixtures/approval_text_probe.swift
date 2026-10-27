import Foundation
let base:[String:String] = ["version":"RSBA2","policy":"companion","mac_id":"mac","workspace_id":"ws","run_id":"run","contract_sha256":String(repeating:"11",count:32),"inputs_sha256":String(repeating:"22",count:32),"bounds":"bounds","nonce":String(repeating:"bb",count:32),"expiry_unix":"1700000000","companion_key_id":"phone","companion_generation":"1"]
var failures=0
for key in ["mac_id","workspace_id","run_id","bounds"] {
 for hostile in ["line\nPolicy: local", "bidi\u{202e}", "hidden\u{200b}"] {
  var object=base;object[key]=hostile
  do { _ = try RSBA2Package.parse(JSONSerialization.data(withJSONObject:object)); print("FAIL accepted \(key): \(hostile.debugDescription)");failures += 1 } catch {}
 }
}
exit(failures == 0 ? 0 : 1)
