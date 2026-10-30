-- Create the dashboard service after the image has been pushed (see deploy/deploy.sh).
-- The spec is inline so this file is self-contained. Names must match your .env and deploy/setup.sql.

USE ROLE PIPELINE_ROLE;

CREATE SERVICE IF NOT EXISTS PIPELINE_DB.PIPELINE_TEMPLATE.PIPELINE_APP
  IN COMPUTE POOL PIPELINE_POOL
  FROM SPECIFICATION $$
spec:
  containers:
    - name: app
      image: /PIPELINE_DB/PIPELINE_TEMPLATE/IMAGES/pipeline-template:latest
      env:
        APP_ENV: production
        SNOWFLAKE_DATABASE: PIPELINE_DB
        SNOWFLAKE_SCHEMA: PIPELINE_TEMPLATE
        SNOWFLAKE_WAREHOUSE: PIPELINE_WH
        SNOWFLAKE_STAGE: DOCUMENTS
        TABLE_PREFIX: tpl_
        CORTEX_MODEL: mistral-large2
      secrets:
        - snowflakeSecret: PIPELINE_DB.PIPELINE_TEMPLATE.APP_SECRET_KEY
          secretKeyRef: secret_string
          envVarName: SECRET_KEY
  endpoints:
    - name: app
      port: 8080
      public: true      # reachable by Snowflake users who have access to the service's endpoint
$$
  MIN_INSTANCES = 1 MAX_INSTANCES = 1;

-- URL to open (requires a Snowflake login with the right role):
SHOW ENDPOINTS IN SERVICE PIPELINE_DB.PIPELINE_TEMPLATE.PIPELINE_APP;

-- Scheduled parsing of new files: run the same image as a job service on a schedule.
-- (Example only: check the current EXECUTE JOB SERVICE / TASK documentation before enabling.)
-- CREATE TASK PIPELINE_DB.PIPELINE_TEMPLATE.PARSE_NEW
--   WAREHOUSE = PIPELINE_WH SCHEDULE = '15 MINUTE'
-- AS
--   EXECUTE JOB SERVICE IN COMPUTE POOL PIPELINE_POOL NAME = PIPELINE_DB.PIPELINE_TEMPLATE.PARSE_NEW_JOB
--   FROM SPECIFICATION $$
--   spec:
--     containers:
--       - name: job
--         image: /PIPELINE_DB/PIPELINE_TEMPLATE/IMAGES/pipeline-template:latest
--         command: ["python", "scripts/run_pipeline.py", "parse-new"]
--         env: { SNOWFLAKE_DATABASE: PIPELINE_DB, SNOWFLAKE_SCHEMA: PIPELINE_TEMPLATE, SNOWFLAKE_WAREHOUSE: PIPELINE_WH }
--   $$;
