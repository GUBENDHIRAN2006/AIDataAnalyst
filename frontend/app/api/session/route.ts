import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function GET() {
  const jar = await cookies();
  const email = jar.get("auth_email")?.value ?? "";
  const accessToken = jar.get("auth_access")?.value ?? "";
  return NextResponse.json({
    authenticated: Boolean(accessToken),
    email: accessToken ? email : "",
  });
}
