
import subprocess
import sys

def run():
    print('Starting test_api...')
    subprocess.run([sys.executable, 'test_api.py'])
    print('Done test_api.')
    print('Starting eval_bird baseline...')
    subprocess.run([
        sys.executable, 'verisql/eval_bird.py',
        '--pred-source', 'agent',
        '--output', 'test_baseline.jsonl',
        '--limit', '2',
        '--concurrency', '2'
    ])
    print('Done.')

if __name__ == '__main__':
    run()

