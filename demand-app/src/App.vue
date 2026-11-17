<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'

onLaunch(() => {
  // 需求端为游客优先：不强制登录，只有下单/订单页才校验令牌
  console.log('hhlg demand app launched')
})
</script>

<style>
page {
  background: #f2f6fb;
  color: #0f2233;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
}

/* ===== 通用原子样式 ===== */
.page { min-height: 100vh; padding-bottom: 24rpx; }
.card {
  background: #ffffff;
  border-radius: 20rpx;
  padding: 28rpx;
  margin: 20rpx 24rpx;
  box-shadow: 0 6rpx 20rpx rgba(15, 58, 96, 0.06);
}
.row { display: flex; align-items: center; }
.between { display: flex; align-items: center; justify-content: space-between; }
.muted { color: #7d8fa3; }
.small { font-size: 24rpx; }
.mono { font-family: 'SFMono-Regular', Consolas, monospace; }
.price { color: #0a8f96; font-weight: 700; }
.tag {
  display: inline-block;
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  font-size: 22rpx;
  line-height: 1.6;
}
.tag-green { background: #e4f7ee; color: #12805a; }
.tag-blue { background: #e7f1fe; color: #1d5fbf; }
.tag-orange { background: #fff2e2; color: #b9660b; }
.tag-red { background: #fdeaea; color: #bf2c2c; }
.tag-grey { background: #eef2f7; color: #63788f; }
.btn {
  background: linear-gradient(135deg, #12b3b8, #0a7fa3);
  color: #fff;
  border: none;
  border-radius: 999rpx;
  padding: 22rpx 0;
  font-size: 30rpx;
  font-weight: 600;
  text-align: center;
}
.btn[disabled] { opacity: 0.5; }
.btn-ghost {
  background: #fff;
  color: #0a7fa3;
  border: 1rpx solid #bfe3ea;
}
.empty {
  padding: 80rpx 0;
  text-align: center;
  color: #8a9bad;
  font-size: 26rpx;
}
</style>
