# Setup Guide

## Considerations

SAT cretes a new security_analysis database and Delta tables. If you are an existing SAT user please run the following command:

### Hive metastore based schema

```sql
  drop  database security_analysis cascade;
```

### Unity Catalog based schema

```sql
  drop  database <uc_catalog_name>.security_analysis cascade;
```

## Pre-requisites
