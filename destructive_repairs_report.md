# VeriSQL Repair Impact Analysis

This report compares the initial SQL generation (No Repair) vs the final SQL after the Verification & Repair loop.

## Destructive Repairs (4 cases)
*These are cases where the initial SQL was **CORRECT** (EX=1), but the Verifier falsely flagged it and the Repair module made it **INCORRECT** (EX=0).*

### Q610 (codebase_community)
**Question:** What are the names of badges that users who have the highest reputation obtained?

**1. Initial Correct SQL (No Repair)**:
```sql
SELECT b.Name
FROM badges b
INNER JOIN users u ON b.UserId = u.Id
WHERE u.Reputation = (SELECT MAX(Reputation) FROM users)
```

**2. Verifier Errors Triggered (The False Positives)**:

**3. Final Broken SQL (After 3 iterations)**:
```sql
SELECT DISTINCT b.Name
FROM badges b
INNER JOIN users u ON b.UserId = u.Id
WHERE u.Reputation = (SELECT MAX(Reputation) FROM users)
```

---
### Q766 (superhero)
**Question:** What is the hero's full name with the highest attribute in strength?

**1. Initial Correct SQL (No Repair)**:
```sql
SELECT s.full_name
FROM superhero s
JOIN hero_attribute ha ON s.id = ha.hero_id
JOIN attribute a ON ha.attribute_id = a.id
WHERE a.attribute_name = 'Strength'
AND ha.attribute_value = (
    SELECT MAX(ha2.attribute_value)
    FROM hero_attribute ha2
    JOIN attribute a2 ON ha2.attribute_id = a2.id
    WHERE a2.attribute_name = 'Strength'
)
```

**2. Verifier Errors Triggered (The False Positives)**:

**3. Final Broken SQL (After 3 iterations)**:
```sql
SELECT s.full_name
FROM superhero s
JOIN hero_attribute ha ON s.id = ha.hero_id
JOIN attribute a ON ha.attribute_id = a.id
WHERE a.attribute_name = 'strength'
AND ha.attribute_value = (
    SELECT MAX(ha2.attribute_value)
    FROM hero_attribute ha2
    JOIN attribute a2 ON ha2.attribute_id = a2.id
    WHERE a2.attribute_name = 'strength'
)
```

---
### Q1284 (thrombosis_prediction)
**Question:** For the patient with the highest lactate dehydrogenase in the normal range, when was his or her data first recorded?

**1. Initial Correct SQL (No Repair)**:
```sql
SELECT P."First Date"
FROM Patient P
JOIN Laboratory L ON P.ID = L.ID
WHERE L.LDH = (
    SELECT MAX(LDH) 
    FROM Laboratory 
    WHERE LDH < 500
)
AND L.LDH < 500
```

**2. Verifier Errors Triggered (The False Positives)**:
- `Verification failed: 'int' object has no attribute 'as_ast'`
- `Verification failed: 'int' object has no attribute 'as_ast'`
- `Verification failed: sort mismatch`
- `Verification failed: 'int' object has no attribute 'as_ast'`

**3. Final Broken SQL (After 3 iterations)**:
```sql
SELECT P.Description
FROM Patient P
JOIN Laboratory L ON P.ID = L.ID
WHERE L.LDH = (
    SELECT MAX(LDH)
    FROM Laboratory
    WHERE LDH < 500
)
```

---
### Q1517 (debit_card_specializing)
**Question:** For the earliest customer, what segment did he/she have?

**1. Initial Correct SQL (No Repair)**:
```sql
SELECT c.Segment
FROM customers c
JOIN transactions_1k t ON c.CustomerID = t.CustomerID
WHERE t.Date = (SELECT MIN(Date) FROM transactions_1k)
```

**2. Verifier Errors Triggered (The False Positives)**:

**3. Final Broken SQL (After 0 iterations)**:
```sql
SELECT Segment 
FROM customers 
WHERE CustomerID = (SELECT MIN(CustomerID) FROM customers)
```

---
## Beneficial Repairs (0 cases)
*These are cases where the initial SQL was **INCORRECT** (EX=0), but the Repair module successfully fixed it to **CORRECT** (EX=1).*

