// 可参数化的单端口同步音频缓存。
// 顶层当前将其配置为 65,536 x 8 bit，用于保存 PDM 解码后的 PCM 近似样本。
// 同一时钟沿可写入 mem[addr] 并读取该地址；在本设计中录音和回放不并发，
// 因此单地址端口已足够，且这种写法便于综合工具推断片上存储资源。
module audio_buffer #(
    parameter DEPTH = 8192, // 可存储的样本数量，必须为 2 的幂以匹配地址宽度。
    parameter WIDTH = 8     // 每个样本的数据位宽。
) (
    input  wire                     clk,  // 读写使用的同步时钟。
    input  wire                     we,   // 写使能，高电平时把 din 写入 addr。
    input  wire [$clog2(DEPTH)-1:0] addr, // 当前共享读/写地址。
    input  wire [WIDTH-1:0]         din,  // 写入存储器的数据。
    output reg  [WIDTH-1:0]         dout  // 在时钟沿后更新的同步读数据。
);

    // 地址位数由缓存深度自动推导；保留该局部参数便于理解并与端口表达式对应。
    localparam ADDR_W = $clog2(DEPTH);

    // 以寄存器数组描述片上样本存储空间。
    reg [WIDTH-1:0] mem [0:DEPTH-1];

    // 同步写与同步读：we 有效时写入当前地址；无论是否写入，dout 都在
    // 时钟沿后取得该地址的存储值。这一拍读延迟需要由上层播放逻辑考虑。
    always @(posedge clk) begin
        if (we)
            mem[addr] <= din;
        dout <= mem[addr];
    end

endmodule
