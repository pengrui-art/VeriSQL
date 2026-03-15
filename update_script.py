import re

with open('verisql/eval_bird.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace imports
content = content.replace('from tqdm import tqdm', 'import asyncio\nimport time\nfrom tqdm import tqdm\nfrom verisql.eval_utils import CheckpointManager, MetricsCalculator')

# 2. Add safely_run_single and eval_concurrently and replace main
orchestrator_code = """def safely_run_single(item, db_path, schema_info, pred_source):
    start = time.time()
    try:
        res = run_single(item, db_path, schema_info, pred_source)
    except Exception as e:
        res = {
            "question_id": item.get("question_id"),
            "db_id": item.get("db_id"),
            "error": str(e),
            "ex": 0,
            "pred_exec_ok": False
        }
    res["latency"] = time.time() - start
    return res

async def eval_concurrently(data, db_root, pred_source, concurrency, checkpoint_mgr):
    sem = asyncio.Semaphore(concurrency)
    
    async def process(item):
        async with sem:
            db_id = item["db_id"]
            db_dir = Path(db_root) / db_id
            db_path = db_dir / f"{db_id}.sqlite"
            
            if not db_path.exists():
                res = {
                    "question_id": item.get("question_id"),
                    "db_id": db_id,
                    "error": f"missing db file: {db_path}",
                    "ex": 0,
                    "pred_exec_ok": False
                }
            else:
                # Load schema synchronously (fast enough)
                schema_info = load_schema_from_sqlite(db_path)
                load_bird_descriptions(schema_info, db_dir)
                
                # Execute long-running agent logic in thread pool
                res = await asyncio.to_thread(safely_run_single, item, db_path, schema_info, pred_source)
            
            checkpoint_mgr.append_result(res)
            return res

    tasks = [asyncio.create_task(process(item)) for item in data]
    
    for _ in tqdm(asyncio.as_completed(tasks), total=len(data), desc="Evaluating Concurrent"):
        await _

def main():
    parser = argparse.ArgumentParser(description="VeriSQL BIRD Evaluation")
    parser.add_argument("--data", type=str, default="verisql/DataBase/Bird/dev_20240627/dev_tied_append.json")
    parser.add_argument("--db-root", type=str, default="verisql/DataBase/Bird/dev_20240627/dev_databases")
    parser.add_argument("--limit", type=int, default=10000, help="Limit number of questions")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N questions")
    parser.add_argument("--db-id", type=str, default=None, help="Only evaluate a specific db_id")
    parser.add_argument("--pred-source", type=str, choices=["agent", "gold"], default="agent", help="Use output, or gold SQL")
    parser.add_argument("--output", type=str, default="bird_results.jsonl", help="Output file (JSONL format)")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent validations")
    args = parser.parse_args()

    data_path = Path(args.data)
    db_root = Path(args.db_root)
    if not data_path.exists():
        raise FileNotFoundError(f"BIRD data not found: {data_path}")
    if not db_root.exists():
        raise FileNotFoundError(f"BIRD db root not found: {db_root}")

    data = load_json(data_path)
    if args.db_id:
        data = [x for x in data if x.get("db_id") == args.db_id]
    if args.offset:
        data = data[args.offset :]
    data = data[: args.limit]

    # 1. Checkpointing Logic
    checkpoint_mgr = CheckpointManager(args.output)
    completed_ids = checkpoint_mgr.load_completed()
    to_do = [d for d in data if d.get("question_id") not in completed_ids]

    print(f"Dataset Size: {len(data)} | Checkpointed: {len(completed_ids)} | Remaining to run: {len(to_do)}")

    # 2. Async Concurrent Execution
    if to_do:
        asyncio.run(eval_concurrently(to_do, db_root, args.pred_source, args.concurrency, checkpoint_mgr))

    # 3. Read all lines to aggregate metrics
    all_results = []
    with open(args.output, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    all_results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    metrics = MetricsCalculator.compute(all_results)
    metrics["pred_source"] = args.pred_source
    metrics["data"] = str(data_path)

    # 4. Dump Summary
    summary_path = str(args.output).replace('.jsonl', '_summary.json')
    if summary_path == args.output:
        summary_path = args.output + '_summary.json'
        
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics}, f, ensure_ascii=False, indent=2)

    print("\\nEvaluation Complete:")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
"""

content = re.sub(r'def main\(\):.*', orchestrator_code, content, flags=re.DOTALL)

with open('verisql/eval_bird.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done updating!")
