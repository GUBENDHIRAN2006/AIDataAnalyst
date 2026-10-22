export const ADMIN_EMAIL = "gubendhiran0710@gmail.com";

export function isAdminEmail(email: string): boolean {
  return email.trim().toLowerCase() === ADMIN_EMAIL;
}
