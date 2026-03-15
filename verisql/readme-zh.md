# VeriSQL锛氶潰鍚戞暟鎹簱鍒嗘瀽鏅鸿兘浣撶殑绁炵粡绗﹀彿杩愯鏃堕獙璇?

涓€绉嶅叿澶囧舰寮忓寲姝ｇ‘鎬т繚闅滅殑鏂囨湰杞琒QL锛圱ext-to-SQL锛夊彲楠岃瘉鏅鸿兘浣撴灦鏋勩€?

## 馃幆 鏍稿績鍒涙柊鐐?

VeriSQL 閫氳繃浠ヤ笅鏂瑰紡灏?*娣峰悎楠岃瘉**涓?*澶ц瑷€妯″瀷鏅鸿兘浣擄紙LLM Agents锛?* 鐩哥粨鍚堬細
1. **娣峰悎楠岃瘉**锛氥€岄潤鎬侊紙Z3姹傝В鍣級+ 鍔ㄦ€侊紙娌欑鎵ц锛夈€嶅弻閲嶆牎楠屾満鍒躲€?
2. **鍙岃矾寰勭敓鎴?*锛氬悓姝ョ敓鎴怱QL璇彞涓庣嚎鎬ф椂搴忛€昏緫锛圠TL锛夎鏍艰鏄庛€?
3. **鑷姩褰㈠紡鍖栧櫒锛圛LR锛?*锛氬熀浜庝腑闂撮€昏緫琛ㄧず锛圛ntermediate Logic Representation锛夋秷闄よ涔夋涔夈€?
4. **瀵规姉鎬фā鎷熸暟鎹?*锛氱敓鎴愬井鍨嬫暟鎹簱锛圡icro-DB锛夌敤浜庤竟鐣屽満鏅祴璇曘€?
5. **杩借釜寮曞淇**锛氱粨鍚堝叿浣撳弽渚嬬殑鍙嶉寰幆鏈哄埗銆?

## 馃搧 椤圭洰缁撴瀯 & 鏂囦欢璇存槑

```
verisql/
鈹溾攢鈹€ agents/                 # 鏅鸿兘浣撳伐浣滄祦妯″潡
鈹?  鈹溾攢鈹€ graph.py            # LangGraph宸ヤ綔娴佸畾涔?
鈹?  鈹溾攢鈹€ nodes.py            # 宸ヤ綔娴佽妭鐐瑰疄鐜?
鈹?  鈹斺攢鈹€ state.py            # 鐘舵€佹暟鎹ā鍨嬪畾涔?
鈹溾攢鈹€ core/                   # 褰㈠紡鍖栬〃绀哄眰
鈹?  鈹溾攢鈹€ ilr.py              # 涓棿閫昏緫琛ㄧず锛圛LR锛夊畾涔?
鈹?  鈹溾攢鈹€ dsl.py              # 绾︽潫棰嗗煙鐗瑰畾璇█锛圖SL锛夊畾涔?
鈹?  鈹斺攢鈹€ ltl_compiler.py     # LTL鍏紡缂栬瘧鍣?
鈹溾攢鈹€ modules/                # 楠岃瘉涓庝慨澶嶆ā鍧?
鈹?  鈹溾攢鈹€ dynamic_verifier.py # 鍔ㄦ€侀獙璇佸櫒
鈹?  鈹斺攢鈹€ fault_localizer.py  # 鏁呴殰瀹氫綅鍣?
鈹溾攢鈹€ utils/                  # 宸ュ叿绫绘ā鍧?
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ diagnosis.py        # SQL閿欒璇婃柇宸ュ叿
鈹?  鈹溾攢鈹€ spec_utils.py       # 瑙勬牸璇存槑瑙ｆ瀽宸ュ叿
鈹?  鈹斺攢鈹€ z3_utils.py         # Z3绗﹀彿楠岃瘉宸ュ叿
鈹溾攢鈹€ DataBase/
鈹?  鈹斺攢鈹€ Bird/               # BIRD鍩哄噯娴嬭瘯鏁版嵁闆嗭紙寮€鍙戦泦 + 璁粌闆嗭級
鈹溾攢鈹€ app.py                  # Gradio Web鐣岄潰鍏ュ彛
鈹溾攢鈹€ cli.py                  # 鍛戒护琛屽伐鍏峰叆鍙?
鈹溾攢鈹€ config.py               # 鍏ㄥ眬閰嶇疆妯″潡
鈹溾攢鈹€ create_sample_db.py     # 娴嬭瘯鏁版嵁搴撶敓鎴愯剼鏈?
鈹溾攢鈹€ eval_bird.py            # BIRD鍩哄噯娴嬭瘯璇勪及鑴氭湰
鈹溾攢鈹€ main.py                 # 绋嬪簭寮忚皟鐢ㄥ叆鍙?
鈹溾攢鈹€ requirements.txt        # 渚濊禆娓呭崟
鈹斺攢鈹€ test_*.py               # 鍗曞厓/闆嗘垚娴嬭瘯鏂囦欢
```

---

### `agents/` 鈥?LangGraph 宸ヤ綔娴?

#### `agents/graph.py`
瀹氫箟**LangGraph `StateGraph`**锛岀紪鎺掓暣涓猇eriSQL娴佹按绾裤€傛寜浠ヤ笅椤哄簭鏋勫缓骞惰繛鎺ユ墍鏈夎妭鐐癸細

```
鎰忓浘瑙ｆ瀽鍣?鈫?鑷姩褰㈠紡鍖栧櫒 鈫?SQL鐢熸垚鍣?鈫?瑙勬牸璇存槑鐢熸垚鍣?
    鈫?绗﹀彿楠岃瘉鍣?鈫?鍔ㄦ€侀獙璇佸櫒
        鈹€鈹€鈹€ 閫氳繃 鈹€鈹€鈫?鎵ц鍣?鈫?缁撴潫
        鈹€鈹€鈹€ 澶辫触 鈹€鈹€鈫?褰㈠紡鍖栦慨澶嶅櫒 鈫?SQL鐢熸垚鍣紙寰幆锛屾渶澶?娆★級
        鈹€鈹€鈹€ 杈句笂闄?鈹€鈹€鈫?缁撴潫锛堣繑鍥為敊璇級
```

鏍稿績鍑芥暟锛歚compile_verisql_app()` 鈥?杩斿洖缂栬瘧瀹屾垚銆佸彲璋冪敤鐨凩angGraph搴旂敤瀹炰緥銆?

#### `agents/nodes.py`
瀹炵幇**鎵€鏈夊湪宸ヤ綔娴佷腑鎵ц鐨凩angGraph鑺傜偣鍑芥暟**銆傛瘡涓妭鐐逛粠`VeriSQLState`璇诲彇鏁版嵁锛岃皟鐢ㄤ竴涓垨澶氫釜LLM鎻愮ず璇?楠岃瘉鍣ㄦā鍧楋紝骞跺皢缁撴灉鍐欏洖鐘舵€併€?

| 鑺傜偣 | 鍔熻兘 |
|---|---|
| `intent_parser_node` | 灏嗚嚜鐒惰瑷€鏌ヨ瑙ｆ瀽涓虹粨鏋勫寲鎰忓浘JSON锛堟搷浣滅被鍨嬨€佸疄浣撱€佹椂闂磋寖鍥淬€佽繃婊ゆ潯浠讹級 |
| `auto_formalizer_node` | 灏嗚В鏋愬悗鐨勬剰鍥捐浆鎹负ILR锛堜腑闂撮€昏緫琛ㄧず锛?|
| `sql_generator_node` | 鍩轰簬ILR閫氳繃鎬濈淮閾撅紙Chain-of-Thought锛夋彁绀虹敓鎴怱QL锛涢伒寰钩灞€澶勭悊绛栫暐 |
| `spec_generator_node` | 浠嶪LR鐢熸垚鐢ㄤ簬褰㈠紡鍖栭獙璇佺殑DSL `ConstraintSpec`锛堢害鏉熻鏍硷級 |
| `symbolic_verifier_node` | 璋冪敤鍩轰簬Z3鐨刞SymbolicVerifier`锛岄潤鎬佹牎楠孲QL鏄惁绗﹀悎瑙勬牸璇存槑 |
| `dynamic_verifier_node` | 鍦ㄥ鎶楁€у井鍨嬫暟鎹簱涓婃墽琛孲QL锛屾娴嬭繍琛屾椂杩濊琛屼负 |
| `formal_repair_node` | 璋冪敤`FaultLocalizer`锛岀敓鎴愮粨鏋勫寲`PatchAction`锛堣ˉ涓佹搷浣滐級锛岄噸鏋勫弽棣堜俊鎭?|
| `executor_node` | 鍦ㄧ湡瀹濻QLite鏁版嵁搴撲笂鎵ц宸查獙璇佺殑SQL锛屽苟杩斿洖缁撴灉 |

鍚屾椂鍖呭惈`create_llm()` 鈥?宸ュ巶鍑芥暟锛屽垱寤洪拡瀵瑰綋鍓嶆湇鍔″晢锛圤penAI / 娣卞害姹傜储 / 閫氫箟鍗冮棶锛夐厤缃殑`ChatOpenAI`瀹炰緥銆?

#### `agents/state.py`
瀹氫箟鎵€鏈?*Pydantic鏁版嵁妯″瀷**鍜屽湪鍥句腑娴佽浆鐨刞VeriSQLState`绫诲瀷瀛楀吀锛圱ypedDict锛夈€?

| 妯″瀷 | 鎻忚堪 |
|---|---|
| `VeriSQLState` | 涓诲伐浣滄祦鐘舵€侊細鎼哄甫鏌ヨ璇彞銆佹暟鎹簱妯″紡銆両LR銆丼QL銆佽鏍艰鏄庛€侀獙璇佺粨鏋溿€佷慨澶嶅巻鍙插拰鏈€缁堣緭鍑?|
| `VerificationResult` | 楠岃瘉缁撴灉锛坄閫氳繃/澶辫触/閿欒/璺宠繃`锛夈€佸弽渚嬪強姣忎竴姝ョ殑璇︾粏淇℃伅 |
| `PatchActionType` | 缁撴瀯鍖栦慨澶嶆搷浣滅被鍨嬫灇涓撅紙`娣诲姞璋撹瘝`銆乣淇杈圭晫`銆乣淇鍒楀悕`绛夛級 |
| `PatchAction` | 瀛愬彞绾т慨澶嶆寚浠わ細鎸囧畾鐩爣瀛愬彞銆佸綋鍓嶄唬鐮佺墖娈靛拰寤鸿鏇挎崲鍐呭 |
| `FaultLocalization` | 灏嗛獙璇佸け璐ュ叧鑱斿埌鍏蜂綋SQL瀛愬彞锛屽苟闄勫甫瀵瑰簲鐨刞PatchAction` |
| `RepairSuggestion` | 瀛樺偍鍦ㄤ慨澶嶅巻鍙叉棩蹇椾腑鐨勯《灞備慨澶嶈褰?|

---

### `core/` 鈥?褰㈠紡鍖栬〃绀哄眰

#### `core/ilr.py`
瀹氫箟**ILR锛堟剰鍥鹃€昏緫琛ㄧず锛?* 妯″紡 鈥?鏍稿績涓棿琛ㄧず灞傦紝瑙ｈ€﹁嚜鐒惰瑷€鐞嗚В涓嶴QL/瑙勬牸璇存槑鐢熸垚杩囩▼锛岄檷浣庡叧鑱斿够瑙夐闄┿€?

鏍稿績Pydantic妯″瀷锛?
- `ILR` 鈥?椤跺眰涓棿琛ㄧず锛氫綔鐢ㄥ煙锛堝疄浣?杩炴帴+鏃堕棿锛夈€佹搷浣滐紙鏌ヨ/鑱氬悎/璁℃暟锛夈€佺害鏉熸潯浠躲€佽緭鍑烘牸寮?
- `FilterConstraint`/`ExistentialConstraint`/`CompositeConstraint` 鈥?绫诲瀷鍖栫害鏉熸瀯寤哄潡
- `TieBreakingStrategy` 鈥?骞冲眬澶勭悊绛栫暐锛坄杩斿洖鎵€鏈夊钩灞€缁撴灉`/`闅忔満杩斿洖涓€涓猔/`涓嶈繑鍥炲钩灞€缁撴灉`锛夛紝鎺у埗SQL鏄惁浣跨敤瀛愭煡璇㈡垨`LIMIT 1`
- `TemporalSpec` 鈥?缁撴瀯鍖栨椂闂磋寖鍥达紙缁濆鏃堕棿銆佺浉瀵规椂闂存垨鍛藉悕鏃堕棿濡俀1-Q4锛?

#### `core/dsl.py`
瀹氫箟**绾︽潫DSL锛堥鍩熺壒瀹氳瑷€锛?* 鈥?涓€绉嶇畝鍖栥€侀€傞厤LLM鐨勯鍩熺壒瀹氳瑷€锛岀敤浜庤〃杈炬煡璇㈢害鏉熴€侺LM鐢熸垚璇SL鑰岄潪鍘熷LTL锛屽啀鐢辩‘瀹氭€х紪璇戝櫒杞崲涓哄舰寮忓寲閫昏緫銆?

| DSL绫诲瀷 | 鎻忚堪 |
|---|---|
| `TemporalConstraint` | 鏃ユ湡鑼冨洿銆佸搴︼紙Q1-Q4锛夈€佸勾浠芥垨鐩稿鏃堕棿杩囨护 |
| `FilterDSL` | 瀛楁绾ф瘮杈冭繃婊わ紙绛変簬銆佷笉绛変簬銆佸ぇ浜庛€佸ぇ浜庣瓑浜庛€佸寘鍚€佹ā绯婂尮閰嶇瓑锛?|
| `AggregateConstraint` | 鑱氬悎鍑芥暟瑙勬牸锛堟眰鍜屻€佸钩鍧囧€笺€佽鏁般€佹渶灏忓€笺€佹渶澶у€硷級 |
| `ExistenceConstraint` | 瀛樺湪/涓嶅瓨鍦ㄥ瓙鏌ヨ鏍￠獙 |
| `UniquenessConstraint` | 澶氬垪缁勫悎鍞竴鎬х害鏉?|
| `ConstraintSpec` | 椤跺眰瑙勬牸璇存槑锛氫綔鐢ㄥ煙琛?+ `DSLConstraint`鍒楄〃 |

#### `core/ltl_compiler.py`
**纭畾鎬х紪璇戝櫒**锛屽皢`ConstraintSpec`锛圖SL锛夎浆鎹负鐢ㄤ簬Z3楠岃瘉鐨凩TL锛堢嚎鎬ф椂搴忛€昏緫锛夊叕寮忋€傛棤浠讳綍LLM璋冪敤 鈥?绾鍙疯浆鎹㈤€昏緫銆?

鏍稿績绫伙細`LTLCompiler.compile(spec)` 鈥?閫氳繃灏嗘瘡涓狣SL绾︽潫鍒嗗彂鍒扮被鍨嬪寲鐨刞_compile_*`鏂规硶锛岀敓鎴愬舰濡俙鈭€琛?鈭?<琛?: (蠁鈧?鈭?蠁鈧?鈭?鈥?`鐨刞LTLFormula`銆?

---

### `modules/` 鈥?楠岃瘉涓庝慨澶嶆ā鍧?

#### `modules/dynamic_verifier.py`
瀹炵幇**娣峰悎楠岃瘉娴佹按绾跨殑鍔ㄦ€佹牎楠岄儴鍒?*銆備笉渚濊禆鍗曚竴鐨勭鍙?闈欐€佸垎鏋愶紝璇ユā鍧楀悎鎴愬鎶楁€ф暟鎹苟鍦ㄦ矙绠变腑鎵цSQL锛屾娴嬭涓哄眰闈㈢殑杩濊銆?

缁勪欢锛?
- `MockDBGenerator` 鈥?鏋勫缓鏈€灏忓寲寰瀷鏁版嵁搴擄紝鍖呭惈銆岄粍閲戣銆嶏紙婊¤冻鎵€鏈夎鏍肩害鏉燂級鍜屻€屽鎶楄銆嶏紙姣忔杩濆弽涓€涓害鏉燂級銆備篃鍙熀浜嶼3鍙嶄緥鐢熸垚鏁版嵁琛屻€?
- `SandboxExecutor` 鈥?鍦ㄥ唴瀛楽QLite鏁版嵁搴撲腑鎵цSQL锛屾敹闆嗘墽琛岀粨鏋溿€?
- `DynamicVerifier` 鈥?缂栨帓鍣細鐢熸垚妯℃嫙鏁版嵁搴?鈫?鎵цSQL 鈫?鏍￠獙杈撳嚭鏄惁绗﹀悎瑙勬牸 鈫?杩斿洖`VerificationResult`銆?

#### `modules/fault_localizer.py`
瀹炵幇**C3锛堝弽渚嬪紩瀵肩殑缁撴瀯鍖栦慨澶嶏級** 鈥?鍖哄埆浜庢ā绯婃枃鏈弽棣堢殑鏍稿績鐗规€с€?

`FaultLocalizer.localize(sql, spec, verification_result)` 娴佺▼锛?
1. 浣跨敤`sqlglot`灏哠QL瑙ｆ瀽涓烘娊璞¤娉曟爲锛圓ST锛夈€?
2. 閽堝姣忎釜杩濊鐨勮鏍肩害鏉燂紝鍦ˋST涓煡鎵惧搴旂殑璋撹瘝銆?
3. 鏁呴殰鍒嗙被锛歚缂哄け`锛堣皳璇嶄笉瀛樺湪锛夈€乣閿欒`锛堝€奸敊璇級銆乣杈圭晫`锛堝樊涓€閿欒锛夈€?
4. 鐢熸垚鎸囧悜鍏蜂綋SQL瀛愬彞骞跺缓璁慨澶嶆柟妗堢殑`PatchAction`銆?

杈呭姪鍑芥暟锛歚format_patch_actions()` 鈥?灏嗚ˉ涓佸垪琛ㄥ簭鍒楀寲涓虹粨鏋勫寲鎻愮ず瀛楃涓诧紝渚汼QL淇鑺傜偣浣跨敤銆?

---

### `utils/` 鈥?宸ュ叿妯″潡

#### `utils/z3_utils.py`
鎻愪緵**鍩轰簬Z3 SMT鐨勭鍙烽獙璇?*灞傘€?

鏍稿績绫伙細
- `SQLConstraintExtractor` 鈥?浣跨敤`sqlglot`瑙ｆ瀽SQL瀛楃涓诧紝灏哤HERE瀛愬彞璋撹瘝鎻愬彇涓烘爣鍑嗗寲绾︽潫瀛楀吀鍒楄〃銆?
- `SchemaValidator` 鈥?楠岃瘉SQL涓殑鎵€鏈夎〃/鍒楀悕鏄惁瀛樺湪浜巂schema_info`涓紝鍦╖3鎵ц鍓嶆嫤鎴够瑙夌敓鎴愮殑鏍囪瘑绗︺€?
- `SymbolicVerifier` 鈥?灏哠QL绾︽潫鍜岃鏍肩害鏉熺紪鐮佷负Z3鍏紡锛屾牎楠屽彲婊¤冻鎬э紝骞惰繑鍥為檮甯﹀弽渚嬬殑`VerificationResult`銆?

椤跺眰鍑芥暟锛歚verify_sql_against_spec(sql, spec, schema_info)` 鈥?渚涜妭鐐瑰拰CLI浣跨敤鐨勪究鎹峰皝瑁呭嚱鏁般€?

#### `utils/spec_utils.py`
鎻愪緵**椴佹鐨凩LM鐢熸垚`ConstraintSpec` JSON瑙ｆ瀽涓庢竻鐞?*鑳藉姏銆?

鏍稿績鍑芥暟锛?
- `parse_json_from_text(text)` 鈥?鍓ョMarkdown浠ｇ爜鍧椼€佺Щ闄椋庢牸娉ㄩ噴锛屼粠鍘熷LLM杈撳嚭涓彁鍙栨湁鏁圝SON銆?
- `sanitize_constraint(constraint)` 鈥?瑙勮寖鍖栧父瑙丩LM鏍煎紡閿欒锛堝`"time"` 鈫?`"temporal"`锛宍"where"` 鈫?`"filter"`锛夈€?
- `parse_spec_safely(text, scope_table)` 鈥?瀹屾暣娴佹按绾匡細瑙ｆ瀽JSON 鈫?娓呯悊姣忎釜绾︽潫 鈫?鏋勫缓鏈夋晥鐨刞ConstraintSpec`锛岄亣涓嶅彲鎭㈠閿欒鏃跺洖閫€涓虹┖瑙勬牸銆?

#### `utils/diagnosis.py`
鎻愪緵**鏅鸿兘鐨凷QL鎵ц閿欒杩愯鏃惰瘖鏂?*銆?

鏍稿績鍑芥暟锛?
- `diagnose_sql_error(error_msg, schema_info)` 鈥?鍚彂寮忚瘑鍒€屾棤姝ゅ垪銆嶃€屾棤姝よ〃銆嶉敊璇紝骞朵娇鐢╜difflib`寤鸿鏈€鎺ヨ繎鐨勬湁鏁堝悕绉般€?
- `check_result_quality(rows)` 鈥?褰撶粨鏋滆鍖呭惈楂橀噸澶嶇巼鏃跺彂鍑鸿鍛婏紝鎻愮ず鍙兘缂哄け`DISTINCT`鎴朖OIN閿欒銆?

---

### 鏍圭洰褰曟枃浠?

#### `config.py`
鏍稿績**閰嶇疆妯″潡**銆傞€氳繃`python-dotenv`璇诲彇鐜鍙橀噺锛岄厤缃互涓嬪唴瀹癸細
- **LLM鏈嶅姟鍟?*锛歚openai` / `deepseek` / `qwen`锛屽寘鍚悇鏈嶅姟鍟嗙殑API瀵嗛挜鍜屽熀纭€URL銆?
- **妯″瀷鍚嶇О**锛歚SQL_MODEL`銆乣SPEC_MODEL`锛堝悇鏈嶅姟鍟嗛粯璁ゅ€硷級銆?
- **楠岃瘉璁剧疆**锛歚MAX_REPAIR_ITERATIONS`锛堟渶澶т慨澶嶆鏁帮級銆乣Z3_TIMEOUT_MS`锛圸3瓒呮椂鏃堕棿锛夈€乣VERIFICATION_MODE`锛堥獙璇佹ā寮忥級銆?
- **妯″紡杈呭姪閰嶇疆**锛歚TEMPORAL_MAPPINGS`锛圦1-Q4鏃ユ湡鑼冨洿鏄犲皠锛夈€?

鏍稿績鍑芥暟锛歚get_llm_config(provider)` 鈥?杩斿洖鎸囧畾鏈嶅姟鍟嗙殑`{api_key, base_url}`瀛楀吀銆?

#### `main.py`
**绋嬪簭寮忓叆鍙?*锛岀敤浜庡鍗曚釜鑷劧璇█鏌ヨ杩愯VeriSQL銆傚垵濮嬪寲`VeriSQLState`锛岃皟鐢ㄧ紪璇戝悗鐨凩angGraph搴旂敤锛屽苟鎵撳嵃鏍煎紡鍖栫殑璇︾粏鎶ュ憡銆?

浣跨敤鏂瑰紡锛?
```bash
python -m verisql.main "2024骞寸涓夊搴︽椿璺冧骇鍝佺殑鎬婚攢鍞鏄灏戯紵" -v
```

#### `app.py`
**Gradio Web鐣岄潰**锛屾敮鎸佷氦浜掑紡浣跨敤銆?

- `DatabaseManager` 鈥?鍔犺浇SQLite鏂囦欢锛屾彁鍙栨暟鎹簱妯″紡锛屽彲閫夊姞杞紹IRD椋庢牸鐨凜SV璇箟鎻忚堪銆?
- 娴佸紡鏅鸿兘浣撴祦姘寸嚎锛歎I涓彲瀹炴椂鏌ョ湅鍒嗘鎺ㄧ悊杩囩▼銆?
- 灞曠ず鐢熸垚鐨凷QL銆丩TL鍏紡銆侀獙璇佺姸鎬侊紙闈欐€?鍔ㄦ€侊級鍜屾墽琛岀粨鏋溿€?

浣跨敤鏂瑰紡锛?
```bash
python -m verisql.app
```

#### `cli.py`
**鍛戒护琛岀晫闈?*锛屼紭鍖栭€傞厤鎵归噺鍜岃凯浠ｆ祴璇曞満鏅€?

- `CLIDatabaseManager` 鈥?鍛戒护琛岄鏍肩殑鏁版嵁搴撳姞杞藉櫒锛堟敮鎸佹樉寮忔寚瀹歚description_dir`锛夈€?
- 鏀寔閫氳繃闂ID鍔犺浇BIRD `dev.json`涓殑闂銆?
- 杈撳嚭缁撴瀯鍖朖SON锛屼究浜庤嚜鍔ㄥ寲娴佹按绾胯В鏋愩€?
- 纭紪鐮侀粯璁よ矾寰勬寚鍚態IRD `california_schools`鏁版嵁搴擄紝鏂逛究蹇€熸祴璇曘€?

浣跨敤鏂瑰紡锛?
```bash
python -m verisql.cli --db path/to/db.sqlite --question "..."
```

#### `eval_bird.py`
**BIRD鍩哄噯娴嬭瘯璇勪及鑴氭湰**銆?

- 鍔犺浇`dev.json`闂闆嗗拰瀵瑰簲鐨勯粍閲慡QL銆?
- 瀵规瘡涓棶棰樿皟鐢╜run_verisql()`锛屾墽琛岀敓鎴愮殑SQL鍜岄粍閲慡QL锛屽姣旂粨鏋滈泦銆?
- 杩借釜姣忎釜闂鐨勬寚鏍囷紙绮剧‘鍖归厤銆佹墽琛屽噯纭巼銆侀獙璇侀€氳繃鐜囷級銆?
- 鍐欏叆缁撴灉JSON骞舵墦鍗版眹鎬昏〃鏍笺€?

浣跨敤鏂瑰紡锛?
```bash
python verisql/eval_bird.py --dev path/to/dev.json --db-root path/to/dev_databases/
```

#### `create_sample_db.py`
**娴嬭瘯澶瑰叿鐢熸垚鍣?*銆傚垱寤烘渶灏忓寲鐢靛晢SQLite鏁版嵁搴擄紙`sample_store.db`锛夛紝鍖呭惈鍥涘紶琛紙`products`銆乣customers`銆乣orders`銆乣order_items`锛夊苟濉厖绀轰緥鏁版嵁锛岀敤浜庢湰鍦板紑鍙戝拰鍐掔儫娴嬭瘯銆?

#### `test_*.py` 鈥?娴嬭瘯鏂囦欢

| 鏂囦欢 | 瑕嗙洊鑼冨洿 |
|---|---|
| `test_z3_core.py` | Z3绗﹀彿楠岃瘉鍗曞厓娴嬭瘯锛坄SymbolicVerifier`銆乣SchemaValidator`锛?|
| `test_spec_utils.py` | `parse_spec_safely`銆乣sanitize_constraint`銆乣parse_json_from_text`鍗曞厓娴嬭瘯 |
| `test_dynamic_verifier.py` | `MockDBGenerator`鍜宍DynamicVerifier`娴佹按绾垮崟鍏冩祴璇?|
| `test_fault_localizer.py` | `FaultLocalizer`鏁呴殰瀹氫綅鍜宍PatchAction`鐢熸垚鍗曞厓娴嬭瘯 |
| `test_agent_robustness.py` | 绔埌绔櫤鑳戒綋瀵规姉鎬ц緭鍏ラ瞾妫掓€ч泦鎴愭祴璇?|

---

## 馃殌 蹇€熷紑濮?

```bash
# 锛堟帹鑽愶級浠庝粨搴撴牴鐩綍瀹夎
pip install -e .

# 鎴栦粎瀹夎渚濊禆
pip install -r verisql/requirements.txt
```

### 鐜鍙橀噺

鍦╜verisql/`鐩綍鍒涘缓`.env`鏂囦欢锛堟垨鐩存帴瀵煎嚭鐜鍙橀噺锛夛紝閰嶇疆鑷冲皯涓€涓湇鍔″晢锛?

```bash
LLM_PROVIDER=openai  # 鍙€夊€硷細openai | deepseek | qwen

OPENAI_API_KEY=...
# DEEPSEEK_API_KEY=...
# DASHSCOPE_API_KEY=...

# 鍙€夐厤缃?
SQL_MODEL=gpt-4o
SPEC_MODEL=gpt-4o
MAX_REPAIR_ITERATIONS=3
Z3_TIMEOUT_MS=5000
```

### 杩愯锛堢▼搴忓紡 / 鍛戒护琛岋級

```bash
python -m verisql.main "2024骞寸涓夊搴︽椿璺冧骇鍝佺殑鎬婚攢鍞鏄灏戯紵" -v
```

### 杩愯锛圵eb鐣岄潰锛?

```bash
python -m verisql.app
```

### 杩愯锛圔IRD鍩哄噯娴嬭瘯锛?

```bash
python verisql/eval_bird.py \
  --dev verisql/DataBase/Bird/dev_20240627/dev.json \
  --db-root verisql/DataBase/Bird/dev_20240627/dev_databases/
```

## 馃摝 渚濊禆椤?

- `langgraph>=0.1.0` 鈥?鏅鸿兘浣撳伐浣滄祦妗嗘灦
- `langchain>=0.2.0` 鈥?LLM闆嗘垚宸ュ叿
- `z3-solver>=4.12.0` 鈥?SMT楠岃瘉姹傝В鍣?
- `sqlglot>=20.0.0` 鈥?SQL瑙ｆ瀽/鎶借薄璇硶鏍戝鐞?
- `openai>=1.0.0` 鈥?OpenAI鍏煎API瀹㈡埛绔紙涔熺敤浜庢繁搴︽眰绱?閫氫箟鍗冮棶锛?
- `pydantic>=2.0.0` 鈥?鏁版嵁楠岃瘉涓庢ā寮忓畾涔?
- `python-dotenv>=1.0.0` 鈥?鐜鍙橀噺绠＄悊
- `gradio>=4.0.0` 鈥?婕旂ず鐢╓eb鐣岄潰
- `httpx>=0.25.0` 鈥?HTTP瀹㈡埛绔紙閫傞厤澶氭湇鍔″晢锛?
- `pandas>=2.0.0`, `numpy>=1.24.0` 鈥?鍔ㄦ€佹矙绠遍獙璇佸櫒渚濊禆
- `tqdm>=4.0.0` 鈥?鍩哄噯娴嬭瘯杩涘害鏉?

锛堟敞锛氭湰椤圭洰涓虹爺绌跺師鍨嬶級

## 馃専 杩戞湡鏇存柊锛?026骞?鏈堬級

- **Gradio Web鐣岄潰**锛氬畬鏁碪I鏀寔锛屽寘鍚櫤鑳戒綋鎺ㄧ悊杩囩▼娴佸紡杈撳嚭銆丼QL鍙鍖栧拰浜や簰寮忛獙璇佸弽棣堛€?
- **澶歀LM鏀寔**锛氶€氳繃`create_llm`杈呭姪鍑芥暟闆嗘垚OpenAI銆佹繁搴︽眰绱紙DeepSeek锛夊拰閫氫箟鍗冮棶锛圦wen/DashScope锛堿PI銆?
- **澧炲己鍨嬮獙璇?*锛氭柊澧瀈SchemaValidator`锛屽湪绗﹀彿楠岃瘉鍓嶆嫤鎴够瑙夌敓鎴愮殑鍒?琛ㄥ悕銆?
- **杩唬寮忎慨澶?*锛氬疄鐜板弽棣堝惊鐜満鍒讹紝鏅鸿兘浣撴帴鏀堕獙璇侀敊璇悗鑷姩淇SQL锛堟渶澶?娆★級銆?
- **璇箟鎰熺煡**锛氭敮鎸佸姞杞紹IRD椋庢牸鐨凜SV鏍煎紡`database_description`锛屽疄鐜板垪璇箟鐞嗚В銆?
- **缁撴瀯鍖栦慨澶嶏紙C3锛?*锛歚FaultLocalizer` + `PatchAction`鏇夸唬妯＄硦鏂囨湰鍙嶉锛屾彁渚涘瓙鍙ョ骇淇鎸囦护銆
