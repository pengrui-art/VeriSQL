# VeriSQL Repair Quality Report

- Agent run: `paper_data\result_verisql_qwen.jsonl`
- No-repair run: `paper_data\result_norepair_qwen.jsonl`
- Overlap questions: 42
- Repaired cases: 36
- Beneficial repairs: 0
- Destructive repairs: 3
- Neutral repairs: 33

## Patch Action Summary

| Action | Questions | Occurrences | Beneficial | Destructive | Neutral | Success Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

## Beneficial Repairs

_None._

## Destructive Repairs

### Q610 (codebase_community)
**Question:** What are the names of badges that users who have the highest reputation obtained?

**Patch Actions:** N/A

**No-Repair SQL**
```sql
SELECT b.Name
FROM badges b
INNER JOIN users u ON b.UserId = u.Id
WHERE u.Reputation = (SELECT MAX(Reputation) FROM users)
```

**Final SQL**
```sql
SELECT DISTINCT b.Name
FROM badges b
INNER JOIN users u ON b.UserId = u.Id
WHERE u.Reputation = (SELECT MAX(Reputation) FROM users)
```

### Q766 (superhero)
**Question:** What is the hero's full name with the highest attribute in strength?

**Patch Actions:** N/A

**No-Repair SQL**
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

**Final SQL**
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

### Q1284 (thrombosis_prediction)
**Question:** For the patient with the highest lactate dehydrogenase in the normal range, when was his or her data first recorded?

**Patch Actions:** N/A

**No-Repair SQL**
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

**Final SQL**
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

