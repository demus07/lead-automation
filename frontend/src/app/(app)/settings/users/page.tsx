"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Loader2, LogOut, MoreHorizontal, Pencil, Plus, Trash2, UserCheck, UserX, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DataTable, type Column } from "@/components/shared/data-table";
import { Field } from "@/components/shared/field";
import { PageHeader } from "@/components/shared/page-header";
import { Section } from "@/components/shared/section";
import { ToneBadge } from "@/components/shared/tone-badge";
import { useApiMutation } from "@/hooks/use-api-mutation";
import { useCan, useSession } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { fmtRelative, humanize } from "@/lib/format";
import type { Msg, Role, User } from "@/lib/types";

const ROLES: { value: Role; label: string; help: string }[] = [
  { value: "admin", label: "Admin", help: "Everything, including settings, users and mailboxes." },
  { value: "operator", label: "Operator", help: "Research, edit and approve drafts; run workflows." },
  { value: "viewer", label: "Viewer", help: "Read-only access." },
];

const PASSWORD_HINT = "At least 10 characters.";

function RoleSelect({ value, onChange, id }: { value: Role; onChange: (r: Role) => void; id?: string }) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Role)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value}>
            {r.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const createSchema = z.object({
  email: z.string().email("Enter a valid email"),
  full_name: z.string().max(200),
  password: z.string().min(10, PASSWORD_HINT).max(256),
  role: z.enum(["admin", "operator", "viewer"]),
});
type CreateValues = z.infer<typeof createSchema>;

function CreateUserDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const form = useForm<CreateValues>({ resolver: zodResolver(createSchema), defaultValues: { email: "", full_name: "", password: "", role: "operator" } });
  const create = useApiMutation((v: CreateValues) => api.post<User>("/users", v), {
    success: (u) => `User ${u.email} added`,
    invalidate: [["users"]],
    onSuccess: () => {
      form.reset();
      onOpenChange(false);
    },
  });
  const e = form.formState.errors;
  const role = form.watch("role");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add user</DialogTitle>
          <DialogDescription>Share the password with them securely; they can change it after signing in.</DialogDescription>
        </DialogHeader>
        <form id="create-user" className="space-y-4" onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate>
          <Field label="Email" htmlFor="cu-email" error={e.email?.message}>
            <Input id="cu-email" type="email" autoComplete="off" {...form.register("email")} />
          </Field>
          <Field label="Full name" htmlFor="cu-name">
            <Input id="cu-name" {...form.register("full_name")} />
          </Field>
          <Field label="Temporary password" htmlFor="cu-pass" error={e.password?.message} hint={PASSWORD_HINT}>
            <Input id="cu-pass" type="password" autoComplete="new-password" {...form.register("password")} />
          </Field>
          <Field label="Role" htmlFor="cu-role" hint={ROLES.find((r) => r.value === role)?.help}>
            <RoleSelect id="cu-role" value={role} onChange={(r) => form.setValue("role", r)} />
          </Field>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="create-user" disabled={create.isPending}>
            {create.isPending && <Loader2 className="animate-spin" />}
            Add user
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditUserDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const [name, setName] = useState(user.full_name);
  const [role, setRole] = useState<Role>(user.role);
  const save = useApiMutation((body: Record<string, unknown>) => api.patch<User>(`/users/${user.id}`, body), {
    success: "User saved",
    invalidate: [["users"]],
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit {user.email}</DialogTitle>
          <DialogDescription>Changing the role signs the user out of their current sessions.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Full name" htmlFor="eu-name">
            <Input id="eu-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Role" htmlFor="eu-role" hint={ROLES.find((r) => r.value === role)?.help}>
            <RoleSelect id="eu-role" value={role} onChange={setRole} />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={save.isPending}
            onClick={() => {
              const body: Record<string, unknown> = {};
              if (name !== user.full_name) body.full_name = name;
              if (role !== user.role) body.role = role;
              if (Object.keys(body).length === 0) return onClose();
              save.mutate(body);
            }}
          >
            {save.isPending && <Loader2 className="animate-spin" />}
            Save user
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const [pw, setPw] = useState("");
  const reset = useApiMutation(() => api.patch<User>(`/users/${user.id}`, { password: pw }), {
    success: "Password reset",
    invalidate: [["users"]],
  });
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Reset password for ${user.email}`}
      description="Their existing sessions are signed out."
      confirmLabel="Reset password"
      confirmDisabled={pw.length < 10}
      onConfirm={() => reset.mutateAsync()}
    >
      <Field label="New password" htmlFor="rp-pass" hint={PASSWORD_HINT}>
        <Input id="rp-pass" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
      </Field>
    </ConfirmDialog>
  );
}

type Pending = { kind: "edit" | "reset" | "delete" | "deactivate" | "revoke"; user: User } | null;

function UsersAdmin() {
  const me = useSession().data?.user;
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const patch = useApiMutation(({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch<User>(`/users/${id}`, body), {
    success: (u) => (u.is_active ? "User activated" : "User deactivated"),
    invalidate: [["users"]],
  });
  const revoke = useApiMutation((id: string) => api.post<Msg>(`/users/${id}/revoke-sessions`), { success: "Sessions revoked", invalidate: [["users"]] });
  const del = useApiMutation((id: string) => api.delete<Msg>(`/users/${id}`), { success: "User deleted", invalidate: [["users"]] });
  const close = () => setPending(null);

  const columns: Column<User>[] = [
    {
      key: "user",
      header: "User",
      cell: (u) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-medium">
            <span className="truncate">{u.full_name || u.email}</span>
            {u.id === me?.id && <span className="text-xs font-normal text-muted-foreground">you</span>}
          </div>
          {u.full_name && <div className="truncate text-xs text-muted-foreground">{u.email}</div>}
        </div>
      ),
    },
    { key: "role", header: "Role", cell: (u) => <ToneBadge tone={u.role === "admin" ? "brand" : u.role === "operator" ? "info" : "neutral"}>{humanize(u.role)}</ToneBadge> },
    { key: "status", header: "Status", cell: (u) => (u.is_active ? <ToneBadge tone="success" dot>Active</ToneBadge> : <ToneBadge tone="neutral" dot>Deactivated</ToneBadge>) },
    { key: "login", header: "Last sign-in", cell: (u) => <span className="text-sm text-muted-foreground">{fmtRelative(u.last_login_at)}</span>, hideBelow: "md" },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (u) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${u.email}`}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setPending({ kind: "edit", user: u })}>
              <Pencil /> Edit name and role
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setPending({ kind: "reset", user: u })}>
              <KeyRound /> Reset password
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setPending({ kind: "revoke", user: u })}>
              <LogOut /> Revoke sessions
            </DropdownMenuItem>
            {u.id !== me?.id && (
              <>
                <DropdownMenuSeparator />
                {u.is_active ? (
                  <DropdownMenuItem onSelect={() => setPending({ kind: "deactivate", user: u })}>
                    <UserX /> Deactivate
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem onSelect={() => patch.mutate({ id: u.id, body: { is_active: true } })}>
                    <UserCheck /> Activate
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem variant="destructive" onSelect={() => setPending({ kind: "delete", user: u })}>
                  <Trash2 /> Delete
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <Section
      title="Team"
      description="Roles decide what each person can do. The backend enforces the same rules."
      actions={
        <Button onClick={() => setCreating(true)}>
          <Plus /> Add user
        </Button>
      }
      bodyClassName="p-0 [&>div]:p-4"
    >
      <DataTable
        columns={columns}
        rows={q.data}
        rowKey={(u) => u.id}
        isLoading={q.isFetching}
        error={q.error}
        onRetry={() => q.refetch()}
        empty={{ icon: Users, title: "No users" }}
      />
      <CreateUserDialog open={creating} onOpenChange={setCreating} />
      {pending?.kind === "edit" && <EditUserDialog user={pending.user} onClose={close} />}
      {pending?.kind === "reset" && <ResetPasswordDialog user={pending.user} onClose={close} />}
      {pending?.kind === "revoke" && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Revoke sessions for ${pending.user.email}?`}
          description="They'll be signed out everywhere and need to sign in again."
          confirmLabel="Revoke sessions"
          onConfirm={() => revoke.mutateAsync(pending.user.id)}
        />
      )}
      {pending?.kind === "deactivate" && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Deactivate ${pending.user.email}?`}
          description="They're signed out and can't sign in until reactivated. Their history is kept."
          confirmLabel="Deactivate"
          destructive
          onConfirm={() => patch.mutateAsync({ id: pending.user.id, body: { is_active: false } })}
        />
      )}
      {pending?.kind === "delete" && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && close()}
          title={`Delete ${pending.user.email}?`}
          description="The account is removed and signed out. Audit history keeps their past actions."
          confirmLabel="Delete user"
          destructive
          requireText="delete"
          onConfirm={() => del.mutateAsync(pending.user.id)}
        />
      )}
    </Section>
  );
}

const pwSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z.string().min(10, PASSWORD_HINT).max(256),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });
type PwValues = z.infer<typeof pwSchema>;

function ChangePassword() {
  const form = useForm<PwValues>({ resolver: zodResolver(pwSchema), defaultValues: { current_password: "", new_password: "", confirm: "" } });
  const change = useApiMutation(
    (v: PwValues) => api.post<Msg>("/auth/change-password", { current_password: v.current_password, new_password: v.new_password }),
    { success: (r) => r.message || "Password changed", invalidate: [["auth"]], onSuccess: () => form.reset() },
  );
  const e = form.formState.errors;
  return (
    <Section id="password" title="Your password" description="Changing it signs you out of other devices; this session stays signed in.">
      <form className="max-w-sm space-y-4" onSubmit={form.handleSubmit((v) => change.mutate(v))} noValidate>
        <Field label="Current password" htmlFor="pw-cur" error={e.current_password?.message}>
          <Input id="pw-cur" type="password" autoComplete="current-password" {...form.register("current_password")} />
        </Field>
        <Field label="New password" htmlFor="pw-new" error={e.new_password?.message} hint={PASSWORD_HINT}>
          <Input id="pw-new" type="password" autoComplete="new-password" {...form.register("new_password")} />
        </Field>
        <Field label="Confirm new password" htmlFor="pw-confirm" error={e.confirm?.message}>
          <Input id="pw-confirm" type="password" autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        <Button type="submit" disabled={change.isPending}>
          {change.isPending && <Loader2 className="animate-spin" />}
          Change password
        </Button>
      </form>
    </Section>
  );
}

export default function UsersPage() {
  const isAdmin = useCan("admin");
  return (
    <div className="max-w-5xl space-y-8">
      <PageHeader
        title={isAdmin ? "Users" : "Account"}
        description={isAdmin ? "Manage who can access the workspace and what they can do." : "Manage your own sign-in."}
      />
      {isAdmin && <UsersAdmin />}
      <ChangePassword />
    </div>
  );
}
