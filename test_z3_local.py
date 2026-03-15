from z3 import *

x = Int("x")
try:
    print(Implies(True, x == 1))
except Exception as e:
    print(repr(e))
try:
    print(And([]))
except Exception as e:
    print(repr(e))
