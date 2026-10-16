// 임시 표준 펄스 동기화 셀. 사내 표준 셀 이름과 포트를 받으면 바꾼다 (P0 자료).
// 보내는 쪽: d가 1인 src_clk 에지마다 tog를 뒤집는다. 받는 쪽: tog를 2단으로 동기화하고(s1, s2),
// 한 단 더 늦춘 값(s3)과 다르면 q = 1 (dst_clk 한 주기). 펄스 간격은 느린 쪽 클럭 3주기 이상이어야 한다.
// 리셋은 양쪽 모두 active-low 비동기 (0으로).
module sync_pulse (
  input  logic src_clk,
  input  logic src_rst_n,
  input  logic dst_clk,
  input  logic dst_rst_n,
  input  logic d,
  output logic q
);
  logic tog, s1, s2, s3;
  always_ff @(posedge src_clk or negedge src_rst_n) begin
    if (!src_rst_n) tog <= 1'b0;
    else            tog <= tog ^ d;
  end
  always_ff @(posedge dst_clk or negedge dst_rst_n) begin
    if (!dst_rst_n) begin
      s1 <= 1'b0;
      s2 <= 1'b0;
      s3 <= 1'b0;
    end else begin
      s1 <= tog;
      s2 <= s1;
      s3 <= s2;
    end
  end
  assign q = s2 ^ s3;
endmodule
