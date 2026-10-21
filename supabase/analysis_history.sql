-- Run once in the Supabase SQL Editor to enable per-user saved analysis history.
create table if not exists public.analysis_history (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid()
        references auth.users (id) on delete cascade,
    title text not null check (char_length(title) <= 120),
    question text not null check (char_length(question) <= 4000),
    answer text not null check (char_length(answer) <= 12000),
    created_at timestamptz not null default now()
);

alter table public.analysis_history enable row level security;

do $policies$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'analysis_history'
          and policyname = 'analysis_history_select_own'
    ) then
        create policy analysis_history_select_own
            on public.analysis_history for select
            using (auth.uid() = user_id);
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'analysis_history'
          and policyname = 'analysis_history_insert_own'
    ) then
        create policy analysis_history_insert_own
            on public.analysis_history for insert
            with check (auth.uid() = user_id);
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'analysis_history'
          and policyname = 'analysis_history_delete_own'
    ) then
        create policy analysis_history_delete_own
            on public.analysis_history for delete
            using (auth.uid() = user_id);
    end if;
end
$policies$;

grant select, insert, delete on public.analysis_history to authenticated;
