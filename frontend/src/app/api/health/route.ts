import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "healthy",
    service: "aegis-marine-frontend",
    timestamp: new Date().toISOString(),
  });
}
