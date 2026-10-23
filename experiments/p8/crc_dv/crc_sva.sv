// axis_crc_append 동결 RTL(674c)용 SVA. bind로 붙인다. 실패는 [SVA] FAIL 줄로 낸다.
module crc_sva (
  input logic clk, rst,
  input logic s_axis_tvalid, s_axis_tready,
  input logic [7:0] m_axis_tdata, input logic m_axis_tvalid, m_axis_tready, m_axis_tlast, m_axis_tuser,
  input logic [15:0] stat_frames
);
  // valid/ready: 기다리는 동안 valid와 데이터 유지
  a_hold: assert property (@(posedge clk) disable iff (rst)
      m_axis_tvalid && !m_axis_tready |=> m_axis_tvalid && $stable(m_axis_tdata) && $stable(m_axis_tlast) && $stable(m_axis_tuser))
    else $display("[SVA] FAIL a_hold t=%0t", $time);
  // CRC-08: stat_frames는 그대로이거나 1 늘고 0xFFFF 다음은 0
  a_stat: assert property (@(posedge clk) disable iff (rst)
      stat_frames == $past(stat_frames) || stat_frames == 16'($past(stat_frames) + 16'd1))
    else $display("[SVA] FAIL a_stat t=%0t %0d -> %0d", $time, $past(stat_frames), stat_frames);
  // CRC-E01: rst를 본 다음 클럭부터 출력 0
  a_rst: assert property (@(posedge clk) $past(rst) |-> !m_axis_tvalid && !s_axis_tready && stat_frames == 16'd0)
    else $display("[SVA] FAIL a_rst t=%0t", $time);
  c_wrap: cover property (@(posedge clk) disable iff (rst) $past(stat_frames) == 16'hFFFF && stat_frames == 16'd0) $display("[SVA] COVER c_wrap t=%0t", $time);
endmodule

bind axis_crc_append crc_sva u_sva (.*);
