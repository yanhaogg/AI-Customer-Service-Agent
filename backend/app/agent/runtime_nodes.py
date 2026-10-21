"""LangGraph model/tool nodes with bounded execution and safe query failure feedback."""
import json
from time import monotonic
from langchain_core.messages import AIMessage,SystemMessage,ToolMessage
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from .config import AgentUnavailableError


def text_content(message):
    if isinstance(message.content,str):return message.content.strip()
    return '\n'.join(block.get('text','') for block in message.content if isinstance(block,dict) and block.get('type')=='text').strip()


def build_nodes(settings,tools,system_prompt,deadline,model_factory,budget=None,actor=None):
    tools_by_name={tool.name:tool for tool in tools}

    def model_node(state):
        steps=state.get('steps',0)
        remaining=deadline-monotonic()
        if remaining<=0:raise AgentUnavailableError('本轮查询用时较长，请缩小问题后重试。')
        if steps>=settings.max_steps:
            if budget:budget.limited=True
            return {'messages':[AIMessage(content='本轮已达到查询次数上限。请缩小查询范围，或提供商品名称、订单编号后继续。')],
                    'limited':True}
        if budget and not budget.model():
            return {'messages':[AIMessage(content='本轮整体查询次数已达上限，请根据已有查询结果继续处理。')],'limited':True}
        model=model_factory(settings,max(1,min(settings.timeout,remaining)))
        result=model.bind_tools(tools).invoke([SystemMessage(content=system_prompt),*state['messages']])
        if not isinstance(result,AIMessage) or result.invalid_tool_calls:
            raise AgentUnavailableError('模型返回的查询请求格式无效，请重试。')
        if not result.tool_calls and not text_content(result):
            raise AgentUnavailableError('模型未返回有效回复，请重试。')
        return {'messages':[result],'steps':steps+1}

    def tool_node(state):
        count=state.get('tool_calls',0);messages=[];trace=[]
        for call in state['messages'][-1].tool_calls:
            name=call['name'];status='ok'
            if monotonic()>=deadline:raise AgentUnavailableError('本轮查询用时较长，请缩小问题后重试。')
            allowed=budget.tool() if budget else count<settings.max_tools
            if not allowed:
                observation={'error':'本轮查询工具次数已达上限，请基于已有结果回答或请用户缩小范围。'};status='limit'
            elif name not in tools_by_name:
                observation={'error':'工具不存在。只允许已注册的只读查询工具，不能执行退款、支付或数据库写入。'};status='rejected'
            else:
                try:
                    observation=tools_by_name[name].invoke(call.get('args',{}))
                    if isinstance(observation,dict) and observation.get('error'):status='not_found'
                except (ValidationError,TypeError,ValueError):
                    observation={'error':'查询参数不合法。不要传 user_id 等身份字段；按价格筛选必须指定币种，请按工具参数定义重试。'};status='invalid_arguments'
                except (SQLAlchemyError,HTTPException):
                    observation={'error':'数据库查询暂时不可用，请稍后重试，不要编造数据。'};status='unavailable'
            count+=1
            content=json.dumps(observation,ensure_ascii=False,default=str)
            if len(content)>20000:
                content=json.dumps({'error':'查询结果过多，请减少 limit 或查询单款商品、单笔订单。'},ensure_ascii=False)
                status='too_large'
            messages.append(ToolMessage(content=content,tool_call_id=call['id'],name=name))
            trace.append({'name':name[:80],'status':status,**({'agent':actor} if actor else {})})
            if budget:budget.trace.append(trace[-1])
        return {'messages':messages,'tool_calls':count,'trace':trace}

    def route(state):return 'tools' if state['messages'][-1].tool_calls else 'end'
    return model_node,tool_node,route
