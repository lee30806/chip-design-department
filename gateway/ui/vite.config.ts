import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 중에는 게이트웨이(8750)로 API를 넘긴다. 빌드 결과(dist)는 게이트웨이가 정적 파일로 제공한다.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8750" } },
  build: { outDir: "dist", sourcemap: false },
});
