INSERT INTO tasks (
    id, tenant_id, plot_id, device_id, tool, args, reason,
    status, requires_approval, idempotency_key, created_by
) VALUES (
    gen_random_uuid(),
    'f9de8578-f6d9-4c56-8867-0f2fe7b15596',
    '0bc335dd-1edb-41b3-9f3b-a481a6520f3b',
    '739eb6e2-d5cc-4693-86a9-e35c18c536e2',
    'control_irrigation',
    '{"duration_min": 8}'::jsonb,
    'Phase 8c test task for ledger posting',
    'APPROVED',
    false,
    gen_random_uuid(),
    'phase-8c-test'
)
RETURNING id;