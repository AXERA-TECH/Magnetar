# Workflow测试

按照Workflow节点: INIT → EXPORT → COMPILE → VERIFY → SIMULATION → RUNONBOARD 顺序执行

每个节点调用对应的Skill:
 - INIT: magnetar-init
 - EXPORT: magnetar-export
 - COMPILE: magnetar-compile
 - VERIFY: magnetar-verify
 - SIMULATION: magnetar-simulate
 - RUNONBOARD: magnetar-runonboard