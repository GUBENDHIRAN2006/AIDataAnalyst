-- Run in the Supabase SQL Editor. Safe to re-run; legacy rows without a user_id
-- remain unowned and are not visible to any signed-in user.
create table if not exists public.analysis_history (
    id uuid primary key default gen_random_uuid(),
    title text not null check (char_length(title) <= 120),
    question text not null check (char_length(question) <= 4000),
    answer text not null check (char_length(answer) <= 12000),
    created_at timestamptz not null default now()
);

alter table public.analysis_history
    add column if not exists user_id uuid
    references auth.users (id) on delete cascade;

alter table public.analysis_history
    alter column user_id set default auth.uid();

create index if not exists analysis_history_user_created_at_idx
    on public.analysis_history (user_id, created_at desc);

alter table public.analysis_history enable row level security;

-- Remove older permissive policies too: PostgreSQL ORs permissive policies
-- together, so leaving a legacy "everyone can read" policy would defeat RLS.
do $policies$
declare
    existing_policy text;
begin
    for existing_policy in
        select policyname
        from pg_policies
        where schemaname = 'public'
          and tablename = 'analysis_history'
    loop
        execute format(
            'drop policy if exists %I on public.analysis_history',
            existing_policy
        );
    end loop;
end
$policies$;

create policy analysis_history_select_own
    on public.analysis_history for select to authenticated
    using (auth.uid() is not null and user_id = auth.uid());

create policy analysis_history_insert_own
    on public.analysis_history for insert to authenticated
    with check (auth.uid() is not null and user_id = auth.uid());

create policy analysis_history_delete_own
    on public.analysis_history for delete to authenticated
    using (auth.uid() is not null and user_id = auth.uid());

revoke all on table public.analysis_history from anon, authenticated, public;
grant select, insert, delete on table public.analysis_history to authenticated;
