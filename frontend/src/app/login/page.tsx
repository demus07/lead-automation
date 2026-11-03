"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/shared/field";
import { Logo } from "@/components/layout/app-sidebar";
import { api, errorMessage, setCsrfToken } from "@/lib/api";
import type { Session } from "@/lib/types";

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

const STEPS = [
  "Discover companies from directories, hiring threads and search",
  "Research their websites and recent signals",
  "Score website and Company Brain fit independently",
  "Draft outreach and check every claim against evidence",
  "You approve — an unsent draft lands in your mailbox",
  "You send it yourself",
];

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  async function onSubmit(v: Values) {
    setError(null);
    try {
      const s = await api.post<Session>("/auth/login", v);
      setCsrfToken(s.csrf_token);
      qc.setQueryData(["auth", "me"], s);
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <Field label="Email" htmlFor="email" error={form.formState.errors.email?.message}>
        <Input id="email" type="email" autoComplete="username" autoFocus {...form.register("email")} aria-invalid={!!form.formState.errors.email} />
      </Field>
      <Field label="Password" htmlFor="password" error={form.formState.errors.password?.message}>
        <Input id="password" type="password" autoComplete="current-password" {...form.register("password")} aria-invalid={!!form.formState.errors.password} />
      </Field>
      {error && (
        <p className="tone tone-danger rounded-lg border px-3 py-2 text-sm" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" className="h-9 w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting && <Loader2 className="animate-spin" />}
        Sign in
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-svh lg:grid-cols-[1fr_minmax(0,34rem)]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <div className="flex items-center gap-2.5">
          <Logo />
          <span className="font-semibold tracking-[-0.02em]">Agency Growth Engine</span>
        </div>
        <div className="flex flex-1 items-center">
          <div className="w-full max-w-sm space-y-8 py-12">
            <div className="space-y-2">
              <h1 className="text-[1.75rem] font-semibold tracking-[-0.03em]">Sign in</h1>
              <p className="text-sm text-muted-foreground">Use the account your administrator created for you.</p>
            </div>
            <Suspense>
              <LoginForm />
            </Suspense>
          </div>
        </div>
      </div>
      <aside className="hidden border-l bg-sidebar px-12 py-16 lg:flex lg:flex-col lg:justify-center">
        <p className="mb-8 max-w-[30ch] text-xl font-semibold tracking-[-0.02em] text-pretty">
          Every lead is researched and scored. Nothing is sent without you.
        </p>
        <ol className="relative space-y-5 border-l pl-6">
          {STEPS.map((s, i) => (
            <li key={s} className="relative text-sm">
              <span
                className={`absolute top-0.5 -left-[1.95rem] flex size-4 items-center justify-center rounded-full border bg-background text-[0.6rem] font-semibold tabular-nums ${
                  i >= 4 ? "border-brand text-brand" : "text-muted-foreground"
                }`}
              >
                {i + 1}
              </span>
              <span className={i >= 4 ? "font-medium text-foreground" : "text-muted-foreground"}>{s}</span>
            </li>
          ))}
        </ol>
      </aside>
    </main>
  );
}
