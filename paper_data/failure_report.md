# VeriSQL Failure Taxonomy Report

**Source File:** `result_verisql_qwen.jsonl`
**Total Queried:** 42
**Failed Queries:** 21 (Success Rate: 50.00%)

## 1. Execution Errors (Syntax & Schema Hallucinations)
These queries completely failed to run on the sandbox database.

## 2. Logic Errors (Executed Success, but Ex==0)
These queries ran successfully, but the result set did not match the Gold SQL.

### Logic mismatch (Wrong logical plan / missing conditions) (21 cases)
- **Q81 (california_schools)**: In which city can you find the school in the state of California with the lowest latitude coordinates and what is its lowest grade? Indicate the school name.
  - **Gold SQL**: `SELECT T2.City, T1.`Low Grade`, T1.`School Name` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.State = 'CA' AND T2.Latitude IS NOT NULL AND T2.Latitude = (SELECT MIN(Latitude) FROM schools WHERE State = 'CA' AND Latitude IS NOT NULL)`
  - **Pred SQL**: `SELECT City, GSoffered, School
FROM schools
WHERE State = 'CA'
  AND Latitude = (SELECT MIN(Latitude) FROM schools WHERE State = 'CA')`

- **Q82 (california_schools)**: What is the grade span offered in the school with the highest longitude?
  - **Gold SQL**: `SELECT GSoffered FROM schools WHERE ABS(longitude) = (SELECT MAX(ABS(longitude)) FROM schools)`
  - **Pred SQL**: `SELECT GSoffered 
FROM schools 
WHERE Longitude = (SELECT MAX(Longitude) FROM schools)`

- **Q101 (financial)**: List out the accounts who have the earliest trading date in 1995 ?
  - **Gold SQL**: `SELECT account_id FROM trans WHERE STRFTIME('%Y', date) = '1995' ORDER BY date ASC LIMIT 1`
  - **Pred SQL**: `SELECT account_id 
FROM account 
WHERE date >= '1995-01-01' AND date <= '1995-12-31'
  AND date = (
    SELECT MIN(date) 
    FROM account 
    WHERE date >= '1995-01-01' AND date <= '1995-12-31'
  )`

- **Q189 (financial)**: Name the account numbers of female clients who are oldest and have lowest average salary?
  - **Gold SQL**: `SELECT T3.account_id FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id INNER JOIN account AS T3 ON T2.district_id = T3.district_id WHERE T1.gender = 'F' AND T1.birth_date = (SELECT MIN(birth_date) FROM client WHERE gender = 'F') AND T2.A11 = (SELECT MIN(T2.A11) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T1.gender = 'F' AND T1.birth_date = (SELECT MIN(birth_date) FROM client WHERE gender = 'F'))`
  - **Pred SQL**: `SELECT a.account_id
FROM account a
JOIN disp d ON a.account_id = d.account_id
JOIN client c ON d.client_id = c.client_id
JOIN district di ON c.district_id = di.district_id
WHERE c.gender = 'F'
  AND c.birth_date = (SELECT MIN(birth_date) FROM client WHERE gender = 'F')
  AND di.A11 = (SELECT MIN(A11) FROM district)`

- **Q342 (card_games)**: List the card names with value that cost more converted mana for the face.
  - **Gold SQL**: `SELECT name FROM cards WHERE faceConvertedManaCost IS NOT NULL AND faceConvertedManaCost = (SELECT MAX(faceConvertedManaCost)  FROM cards  WHERE faceConvertedManaCost IS NOT NULL)`
  - **Pred SQL**: `SELECT name
FROM cards
WHERE faceConvertedManaCost IS NOT NULL`

- **Q432 (card_games)**: Which Russian set of cards contains the most cards overall?
  - **Gold SQL**: `SELECT T1.id FROM sets AS T1 INNER JOIN set_translations AS T2 ON T1.code = T2.setCode WHERE T2.language = 'Russian' GROUP BY T1.baseSetSize HAVING COUNT(T1.id) = (SELECT MAX(card_count) FROM (SELECT COUNT(T1.id) AS card_count FROM sets AS T1 INNER JOIN set_translations AS T2 ON T1.code = T2.setCode WHERE T2.language = 'Russian' GROUP BY T1.baseSetSize) AS subquery)`
  - **Pred SQL**: `SELECT s.name
FROM sets s
JOIN set_translations st ON s.code = st.setCode
WHERE st.language = 'Russian'
AND s.totalSetSize = (
    SELECT MAX(s2.totalSetSize)
    FROM sets s2
    JOIN set_translations st2 ON s2.code = st2.setCode
    WHERE st2.language = 'Russian'
)`

- **Q515 (card_games)**: When was the oldest mythic card released and what are its legal play formats?
  - **Gold SQL**: `SELECT T1.originalReleaseDate, T2.format FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T1.rarity = 'mythic' AND T1.originalReleaseDate IS NOT NULL AND T2.status = 'Legal' AND T1.originalReleaseDate = (SELECT MIN(originalReleaseDate) FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T1.rarity = 'mythic' AND T1.originalReleaseDate IS NOT NULL AND T2.status = 'Legal')`
  - **Pred SQL**: `SELECT c.originalReleaseDate, l.format
FROM cards c
INNER JOIN legalities l ON c.uuid = l.uuid
WHERE c.rarity = 'mythic'
  AND l.status = 'legal'
  AND c.originalReleaseDate = (
    SELECT MIN(c2.originalReleaseDate)
    FROM cards c2
    INNER JOIN legalities l2 ON c2.uuid = l2.uuid
    WHERE c2.rarity = 'mythic'
      AND l2.status = 'legal'
  )`

- **Q484 (card_games)**: Please list the Italian names of the cards in the set Coldsnap with the highest converted mana cost.
  - **Gold SQL**: `SELECT T2.name FROM foreign_data AS T1 INNER JOIN cards AS T2 ON T2.uuid = T1.uuid INNER JOIN sets AS T3 ON T3.code = T2.setCode WHERE T3.name = 'Coldsnap' AND T1.language = 'Italian' AND T2.convertedManaCost = (SELECT MAX(convertedManaCost) FROM foreign_data AS T1 INNER JOIN cards AS T2 ON T2.uuid = T1.uuid INNER JOIN sets AS T3 ON T3.code = T2.setCode WHERE T3.name = 'Coldsnap' AND T1.language = 'Italian')`
  - **Pred SQL**: `SELECT fd.name
FROM cards c
JOIN foreign_data fd ON c.uuid = fd.uuid
JOIN sets s ON c.setCode = s.code
WHERE s.name = 'Coldsnap'
  AND fd.language = 'Italian'
  AND c.convertedManaCost = (
    SELECT MAX(c2.convertedManaCost)
    FROM cards c2
    JOIN foreign_data fd2 ON c2.uuid = fd2.uuid
    JOIN sets s2 ON c2.setCode = s2.code
    WHERE s2.name = 'Coldsnap'
      AND fd2.language = 'Italian'
  )`

- **Q610 (codebase_community)**: What are the names of badges that users who have the highest reputation obtained?
  - **Gold SQL**: `SELECT T2.name FROM users AS T1 INNER JOIN badges AS T2 ON T1.Id = T2.UserId WHERE T1.Reputation = (SELECT MAX(Reputation) FROM users)`
  - **Pred SQL**: `SELECT DISTINCT b.Name
FROM badges b
INNER JOIN users u ON b.UserId = u.Id
WHERE u.Reputation = (SELECT MAX(Reputation) FROM users)`

- **Q621 (codebase_community)**: What are the name of badges that users who have the lowest reputation obtained?
  - **Gold SQL**: `SELECT T2.Name, T1.Reputation FROM users AS T1 INNER JOIN badges AS T2 ON T1.Id = T2.UserId WHERE T1.Reputation = (SELECT MIN(Reputation) FROM users)`
  - **Pred SQL**: `SELECT b.Name
FROM badges b
INNER JOIN users u ON b.UserId = u.Id
WHERE u.Reputation = (SELECT MIN(Reputation) FROM users)`

