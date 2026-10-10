// 프로젝트 표준 동기화 셀 자리. 실제 셀 이름과 포트는 P0 자료로 받은 뒤 바꾼다.
// 이 파일은 방출 결과의 파싱과 elaboration 검사용이다.
module sync_2ff (
  input  logic clk,
  input  logic rst_n,
  input  logic d,
  output logic q
);
  logic s1;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      s1 <= 1'b0;
      q  <= 1'b0;
    end else begin
      s1 <= d;
      q  <= s1;
    end
  end
endmodule
