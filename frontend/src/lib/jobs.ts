import { toast } from "sonner";

/** Toast for endpoints that start a background workflow job ({job_id, status}). */
export function jobStartedToast(label: string, res: { job_id?: string; status?: string } | null | undefined) {
  const id = res?.job_id;
  toast.success(label, {
    description: res?.status ? `Job ${res.status}. Progress shows on the Automation page.` : undefined,
    action: id
      ? {
          label: "View job",
          onClick: () => {
            window.location.href = `/automation?job=${id}`;
          },
        }
      : undefined,
  });
}
